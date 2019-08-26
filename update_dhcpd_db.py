#!/home/josh/anaconda3/bin/python

# References:
# https://downloads.isc.org/isc/kea/cur/doc/kea-guide.html#dhcp4-std-options
# https://oldkea.isc.org/wiki/HostReservationsHowTo
# https://gitlab.isc.org/isc-projects/kea/wikis/docs/editing-host-reservations
# http://www.lillyrnd.com/index.php/kea-dhcp-server/

import requests, re, csv, yaml, os, sys
import mysql.connector
import ipaddress

class kea_db:
  def __init__(self):
    self.open_database()
    self.mycursor = self.mydb.cursor(buffered=True)

  # ===========================================================================
  @staticmethod
  def mac2int(mac):
  # ===========================================================================
    return int(mac.replace(':', ''),16)

  # ===========================================================================
  @staticmethod
  def int2mac(i):
  # ===========================================================================
    if type(i) == str:
      i = int(i, 16)
    s = hex(i).strip('0x').zfill(12)
    s = re.sub(r'(..)(?=[^$])', r'\1:', s)
    return s

  # ===========================================================================
  @staticmethod
  def ip2int(ip):
  # ===========================================================================
    return int(ipaddress.ip_address(ip))

  # ===========================================================================
  @staticmethod
  def int2ip(i):
  # ===========================================================================
    return str(ipaddress.ip_address(i))

  # ===========================================================================
  @staticmethod
  def ip2hex(ip):
  # ===========================================================================
    return hex(int(ipaddress.ip_address(ip))).strip('0x').zfill(8)

  # ===========================================================================
  @staticmethod
  def ip_list2hex(ip_list):
  # ===========================================================================
    return ''.join(map(kea_db.ip2hex, ip_list))

  # ===========================================================================
  @staticmethod
  def hex_2ip_list(h):
  # ===========================================================================
    return map(lambda t: str(ipaddress.ip_address(int(t, 16))), h)

  # ===========================================================================
  def getHostId(self, mac_address):
  # ===========================================================================
    self.mycursor.execute(f"""select host_id from hosts 
                  where dhcp_identifier =
                   UNHEX('{mac_address.replace(':', '')}');""")
    return self.mycursor.fetchall()

  # ===========================================================================
  def delete_from_database(self, mac_address):
  # ===========================================================================
    hosts_id = self.getHostId(mac_address)
    for host_id in [t[0] for t in hosts_id]:
      self.mycursor.execute(f"delete from dhcp4_options where host_id={host_id};")
      self.mycursor.execute(f"delete from dhcp6_options where host_id={host_id};")
      self.mycursor.execute(f"delete from hosts     where host_id={host_id};")
    self.mydb.commit()

  # ===========================================================================
  def insert_record_to_hosts(self, mac_address, identifier_type, dhcp4_subnet_id, ipv4_address, host_name):
  # ===========================================================================
    sql_insert   = f"""INSERT INTO hosts (dhcp_identifier,
                                          dhcp_identifier_type,
                                          dhcp4_subnet_id,
                                          ipv4_address,
                                          hostname)
                        VALUES (          UNHEX(REPLACE('{mac_address}', ':', '')),
                                          (SELECT type FROM host_identifier_type
                                                WHERE name='{identifier_type}'),
                                          {dhcp4_subnet_id},
                                          INET_ATON('{ipv4_address}'),
                                          '{host_name}');"""

    self.delete_from_database(mac_address)
    self.mycursor.execute(sql_insert)
    self.mycursor.execute("SELECT LAST_INSERT_ID(); ")
    host_id = self.mycursor.fetchone()
    return host_id[0]

  # ===========================================================================
  def set_option(self, host_id, option, value, scope_name='subnet'):
  # ===========================================================================
  # Option codes:  https://www.iana.org/assignments/bootp-dhcp-parameters/bootp-dhcp-parameters.txt
  # space:   # see https://docs.infoblox.com/display/NAG8/About+IPv4+DHCP+Options
    if option == "": return
    if option not in ['routers', 'domain-name-servers']:
      print(f"Option {option} not currently supported")
      sys.exit()

    option_codes = {'routers':             3,
                    'domain-name-servers': 6,
                   }

    dns_options_list = value.replace(' ', '').split(',')
    sql_dns = f"""INSERT INTO dhcp4_options (code, value, space, host_id, scope_id)
                VALUES ({option_codes[option]},
                         UNHEX('{self.ip_list2hex(dns_options_list)}'),
                         'dhcp4',
                         {host_id},
                         (SELECT scope_id FROM dhcp_option_scope
                              WHERE scope_name = '{scope_name}'));"""
    self.mycursor.execute(sql_dns)

  # ===========================================================================
  def print_host_database(self):
  # ===========================================================================
    sql = """SELECT hosts.host_id,
                    hex(hosts.dhcp_identifier),
                    hosts.dhcp_identifier_type, 
                    hosts.dhcp4_subnet_id,
                    hosts.ipv4_address,
                    hosts.hostname
            FROM hosts """
    self.mycursor.execute(sql)
    for host_id, mac, _, subnet_id, addr, hostname, in self.mycursor:
        print(host_id, self.int2mac(mac), subnet_id, self.int2ip(addr), hostname, sep='\t')

  # ===========================================================================
  def print_option_database(self):
  # ===========================================================================
    sql = """SELECT hosts.host_id,
                    hex(hosts.dhcp_identifier),
                    hosts.ipv4_address,
                    hosts.hostname,
                    dhcp4_options.code,
                    hex(dhcp4_options.value),
                    dhcp4_options.space,
                    dhcp4_options.scope_id
        FROM hosts INNER JOIN dhcp4_options
            ON hosts.host_id=dhcp4_options.host_id;"""
    self.mycursor.execute(sql)
    for host_id, mac, addr, hostname, code, value, space, scope_id in self.mycursor:
        value_list = re.findall(r'(........)', value) if value else []
        print(f"{host_id:<7} {self.int2mac(mac):<20} {self.int2ip(addr):<10} {code:>5} {space:>5} {scope_id:>5}   {hostname:<15}", *self.hex_2ip_list(value_list))

  # ===========================================================================
  def open_database(self):
  # ===========================================================================
      with open(os.path.join(os.path.dirname(__file__), "db.yaml"), 'r') as f:
          conf = yaml.load(f, Loader=yaml.BaseLoader)
      db_conf = conf['db']
      self.mydb = mysql.connector.connect(**db_conf)

  # ===========================================================================
  def copy_csv_to_db(self, csv_file_name):
  # ===========================================================================
    f = open(csv_file_name, 'r')
    reader = csv.reader(f, delimiter=',')
    for row in reader:
      host_name, mac_address, ipv4_address, *options_as_list = row
      # convert options list [option1, value1, option2, value2, etc.] to a dictionary
      t = iter(options_as_list)
      options = dict(zip(t, t))  # {option1: value1, option2: value2, etc.}
      host_id = self.insert_record_to_hosts(mac_address, 'hw-address', 1024, ipv4_address, host_name)
      for option in options:
        self.set_option(host_id, option, options[option])
    f.close()
    self.mydb.commit()

def main():
  import sys
  if len(sys.argv) != 2:
    print("Usage: update_dhcp_db.pb <csv_file_name>")
    sys.exit()
  
  if not os.path.isfile(sys.argv[1]):
    print(f"Can't find file '{sys.argv[1]}'")
    sys.exit()

  Kea_DB = kea_db()
  csv_file_name = sys.argv[1]
  Kea_DB.copy_csv_to_db(csv_file_name)

  print("\n\n Hosts Table\n\n")
  Kea_DB.print_host_database()
  print("\n\n Options Table\n\n")
  Kea_DB.print_option_database()

if __name__ == '__main__':
  main()

