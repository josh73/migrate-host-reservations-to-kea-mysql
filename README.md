# Porting Host Reservations from ISC DHCP to Kea MySQL

#### 1. Background

**DHCP** is a network service. A program running on a network server. It allows connecting a new device to a local area network and automatically configuring it to use that network. The device may be a smartphone, a computer or an Internet appliance. Configuring it to use the network includes assigning it an IP address, instructing it on the gateway to use and on other services it requires (e.g., dns for looking up human friendly addresses such as google.com). One of the most popular implementations of **DHCP** is **ISC DHCP** or **dhcpd** which powers much of the Internet.

From Wikipedia:

> **dhcpd** (an abbreviation for "DHCP daemon") is a DHCP server program that operates as a [daemon](https://en.wikipedia.org/wiki/Daemon_(computer_software)) on a [server](https://en.wikipedia.org/wiki/Server_(computing)) to provide [Dynamic Host Configuration Protocol](https://en.wikipedia.org/wiki/Dynamic_Host_Configuration_Protocol) (DHCP) service to a [network](https://en.wikipedia.org/wiki/Computer_network).[[4\]](https://en.wikipedia.org/wiki/DHCPD#cite_note-dhcpd.8-4) This implementation, also known as ISC DHCP, is one of the first and best known, but there are now a number of [other DHCP server software implementations](https://en.wikipedia.org/wiki/Comparison_of_DHCP_server_software) available.

**ISC**, the developer of **ISC DHCP** has released **Kea DHCP**, a new implementation with many improvements over the original. These include:

- Better support of **IPv6**
- Reconfiguration without restart
- Leases and host reservations may optionally be stored in an external database (**MySQL**, **PostreSQL** or **Cassandra**)
- Extensible with optional hooks and libraries
- Better performance.

By default, IP addresses are assigned randomly from a pool. This makes it hard to determine which addresses will be assigned to specific devices. This is normally not a problem but in some cases, deterministic addressing is required. Some examples are file servers, internal web servers and IP cameras. **Host Reservation** is a feature of **dhcpd** and **Kea** that allows deterministic address assignment. It also allows different devices to be assigned different gateways, different dns servers or other options.

With **dhcpd**, Host Reservation is configured in a file (on most linux installations it is: ***/etc/dhcp/dhcpd.conf***). **Kea** offers the option of keeping this configuration in a **MySQL** database.

This tutorial shows how to port the Host Reservation configuration from **dhcpd** to the **Kea** **MySQL** database. It is part of my journey to convert my home Internet gateway to a modern implementation based on ***ubuntu 18.04*** with support for **IPv6** with ***Prefix delegation*** and with a **Kea** **DHCP Server** with **MySQL** database. If you would like to see tutorials covering the other parts of this journey (Setting up a DIY home gateway based on Ubuntu 18.04, installing Kea, setting up traffic monitoring, etc.) please let me know. I will be happy to share what I have learned if there is interest. Also, this tutorial does not yet cover IPv6 aspects.

##### 2. Getting the configuration out of dhcpd and into a user friendly format

For the first step I chose to export the old configuration data to a CSV file. This allows me to easily edit the Host Reservation information before moving it to Kea. Some of the entries in my old configuration are for hosts that no longer exist and other entries could benefit from a review.

This is implemented as a **Python 3** script. The name of the dhcpd configuration file is passed to the program on the command line and is available as `sys.argv[1]`. The configuration program is then read into a string called raw:

```
  with open(sys.argv[1]) as f:
    raw = f.read()
```

Host reservation is implemented in this file using the following format:

```
# An example of host reservation that includes dns and gateways
host myMac {
  hardware ethernet AA:BB:CC:DD:EE:01;
  fixed-address 10.3.1.23;
  option routers 10.3.1.211, 10.3.1.1;
  option domain-name-servers 10.3.1.211, 8.8.8.8;
}
```

```
# An example of host reservation that only includes an IP address
host otherMac {
  hardware ethernet AA:BB:CC:DD:EE:02;
  fixed-address 10.3.1.24;
}
```

Let's read all host information into a list of host records:

`  hosts = re.findall(r'.+?\n\s+host\s+(\S+)\s*{(.+?)}', raw, re.DOTALL)`

Here `re.DOTALL` instructs the `regex` engine to treat the newline character as a regular character.

This expression creates a list of the host information records. The list has a `tuple` per each host containing the host name and the reservation information.

The reservation information is then processed by the function `extract_reservation_params()`. This function receives the tuple and returns the hostname, mac address, ipv4 address and the other options.
```python
def extract_reservation_params(t):
    hostname, items = t
    mac = re.search(r'hardware ethernet\s+(.+?);', items).groups()[0]
    ipv4_address  = re.search(r'fixed-address\s+(.+?);', items).groups()[0]
    other_options = re.findall(r'.+?option (\S+)\s+(\S+);', items, re.DOTALL)
    return hostname, mac, ipv4_address, other_options
```

`other_options` is returned as a list of `tuples`. Each `tuple` has two elements: the option name and the option value.

the information is then stored in a `csv` file, using the `csv` Python library. One row per host. The list of parameters is converted to a simple list which is fed to the `writer.writenow()` method of the `csv` library.

The conversion to a simple list is done by the line:
```python
params = p[:3] + sum(p[3], ())
```

This line, copies the entries p[0], p[1] and p[1] (`hostname`, `mac` and `ipv4 address`) to the new list `params`. It then converts the options from a list of tuples to a simple list and appends it to params. For example the list of tuples may have been:

```python
[('routers', '10.3.1.211, 10.3.1.1'),
  ('domain-name-servers', '10.3.1.211, 8.8.8.8')]
```

The converted list is then:

```python
['routers',
'10.3.1.211, 10.3.1.1',
'domain-name-servers',
'10.3.1.211, 8.8.8.8']
```

The conversion from a list of tuples to a list is done by `sum(list-of-tuples, [])`.

The `csv` file is then created with the format:

```
myMac,AA:BB:CC:DD:EE:F0,10.3.1.23,routers,"10.3.1.211, 10.3.1.1",domain-name-servers,"10.3.1.211, 8.8.8.8"
otherMac,AA:BB:CC:DD:EE:F1,10.3.1.24,,,,
```

#### 2.1 Complete listing of the code to extract the host reservation information from dhcpd to a CSV file

```python
#!/usr/bin/python
import sys, os
import re
import csv

# ======================================================================
def extract_reservation_params(t):
# ======================================================================
    hostname, items = t
    mac           = re.search(r'hardware ethernet\s+(.+?);', items).groups()[0]
    ipv4_address  = re.search(r'fixed-address\s+(.+?);', items).groups()[0]
    other_options = re.findall(r'.+?option (\S+)\s+(\S+);', items, re.DOTALL)
    return hostname, mac, ipv4_address, other_options

# ======================================================================
def main():
# ======================================================================
  if len(sys.argv) != 3:
    print("Usage: parse_dhcpd_config.pb <isc-dicp-file> <csv_file_name>")
    sys.exit()
  
  if not os.path.isfile(sys.argv[1]):
    print(f"Can't find file '{sys.argv[1]}'")
    sys.exit()

  with open(sys.argv[1]) as f:
    raw = f.read()

  hosts = re.findall(r'.+?\n\s+host\s+(\S+)\s*{(.+?)}', raw, re.DOTALL)

  f = open(sys.argv[2], mode='w')
  writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)

  for h in hosts:
    p = extract_reservation_params(h)
    params = p[:3] + sum(p[3], ())    # flatten tuple of strings and tuples to a tuple of strings 
    writer.writerow(params)
    print(params)

  f.close()

# ======================================================================
if __name__ == '__main__':
  main()
```

##### 3. Importing the CSV file into MySQL

The first part of this tutorial extracted the dhcp host reservation information from the **dhcpd** configuration file ***dhcpd.conf*** into a `csv` file. This part takes the information from the `csv` file and imports it to the **MySQL** database used by **kea dhcp**. **Kea** and **dhcpd** have many options and parameters, however this tutorial only deals with the essential ones: mac address, assigned ip address, host name, assigned gateways and assigned dns servers. It should be easy to expand these to include the subnet id and other dhcp options. Also, this tutorial only addresses **IPv4**. If there is interest I can follow up with another tutorial covering **IPv6**.

In our implementation, the **Kea** address reservation is stored in a **MySQL** database called `kea`. It has several tables but for this tutorial we only need to update the `hosts` and the `dhcp4_options` tables.

##### 3.1. MySQL Tables

The `hosts` table has the following columns:

| Column                | Type             | Null | Key | Default | Extra          |
|-----------------------|------------------|------|-----|---------|----------------|
| host_id               | int(10) unsigned | NO   | PRI | NULL    | auto_increment |
| dhcp_identifier       | varbinary(128)   | NO   | MUL | NULL    |                |
| dhcp_identifier_type  | tinyint(4)       | NO   | MUL | NULL    |                |
| dhcp4_subnet_id       | int(10) unsigned | YES  |     | NULL    |                |
| dhcp6_subnet_id       | int(10) unsigned | YES  |     | NULL    |                |
| ipv4_address          | int(10) unsigned | YES  | MUL | NULL    |                |
| hostname              | varchar(255)     | YES  |     | NULL    |                |
| dhcp4_client_classes  | varchar(255)     | YES  |     | NULL    |                |
| dhcp6_client_classes  | varchar(255)     | YES  |     | NULL    |                |
| dhcp4_next_server     | int(10) unsigned | YES  |     | NULL    |                |
| dhcp4_server_hostname | varchar(64)      | YES  |     | NULL    |                |
| dhcp4_boot_file_name  | varchar(128)     | YES  |     | NULL    |                |
| user_context          | text             | YES  |     | NULL    |                |

For this tutorial we only care about the following columns:

|column                 | Description                                                          |
|-----------------------|----------------------------------------------------------------------|
|`host_id`              | An auto-generated integer used as a unique index to the host         |
|`dhcp_identifier`      | Identifies the host. We use the mac address for this but other identifier types can be used |
|`dhcp_identifier_type` | The type of identifier we use. We use the mac address (`hw_address`).  Each identifier type has a numeric code and a descriptive string. The descriptive string (e.g. `hw_address`) can be converted to its numeric code using the table `host_identifier_type`. |
|`dhcpd_subnet_id`      | A unique number associated with a particular subnet. See https://downloads.isc.org/isc/kea/cur/doc/kea-guide.html#ipv4-subnet-id |
|`ipv4_address` | The IPv4 address represented as an unsigned integer |
|`hostname` | The host name as an ASCII string|

For the purpose of this tutorial we do not need to update the other columns.

The `options` table has the following columns:


| Column                | Type             | Null | Key | Default | Extra          |
|-----------------------|------------------|------|-----|---------|----------------|
| option_id         | int(10) unsigned    | NO   | PRI | NULL    | auto_increment |
| code              | tinyint(3) unsigned | NO   |     | NULL    |                |
| value             | blob                | YES  |     | NULL    |                |
| formatted_value   | text                | YES  |     | NULL    |                |
| space             | varchar(128)        | YES  |     | NULL    |                |
| persistent        | tinyint(1)          | NO   |     | 0       |                |
| dhcp_client_class | varchar(128)        | YES  |     | NULL    |                |
| dhcp4_subnet_id   | int(10) unsigned    | YES  |     | NULL    |                |
| host_id           | int(10) unsigned    | YES  | MUL | NULL    |                |
| scope_id          | tinyint(3) unsigned | NO   | MUL | NULL    |                |
| user_context      | text                | YES  |     | NULL    |                |

For our application we only care about the following columns:

|column                 | Description                                                          |
|-----------------------|----------------------------------------------------------------------|
|`option_id`            | An auto-generated integer used as a unique index to the option       |
|`code`                 | A code identifying the option. For example, the `routers` option has the code 3 and the `dns servers` option has the code 6. These codes are defined in https://www.iana.org/assignments/bootp-dhcp-parameters/bootp-dhcp-parameters.txt |
|`value`                | The value assigned to the option. It is stored as a byte sequence, or `blob`. For example a list of IPv4 addresses is stored as a sequence of bytes, 4 bytes per address. |
|`formatted_value`      | An alternative to entering the value as a blob, it is possible to enter it in this column instead, formatted as a text string. We will use the `value` column instead. |
|`space`                 |  DHCP has five predefined option spaces: dhcp, agent, server, nwip, and fqdn. See https://docs.infoblox.com/display/NAG8/About+IPv4+DHCP+Options. In this tutorial the space parameter is always `dhcp4`   |
|`host_id`               | Matches the `host_id` in the `hosts` table to which this option applies  |
|`scope_id`              | May be one of the following: `global`, `subnet`, `client-class` or `host`. Each one may be identified with text description or a numeric integer code. In this tutorial we only use the `subnet` scope which has the numeric value 1. The text descriptions may be converted to the numeric codes using the table `dhcp_option_scope`|


##### 3.2. Importing the Configuration

The configuration is imported by the function `copy_csv_to_db()`. The `csv` file is read, one row at a time. 
The row is then broken into its ingredients by the line:

`host_name, mac_address, ipv4_address, *options_as_list = row`

The first 3 columns in the `csv` file are assigned to `host_name`, `mac_address` and `ipv4_address`. The other columns, containing the dhcp options are assigned as a python list to `options_as_list`. The list has the format [option1, value1, option2, value2, etc.]. We would like to convert the list to a python dictionary of the form: {option1: value1, option2: value2, etc.}. This is done by the following code:

```python
t = iter(options_as_list)
options = dict(zip(t, t))  # {option1: value1, option2: value2, etc.}
```

The first line converts the list into an iterator. The second line then uses `zip()` to pull the values from the iterator, two at a time and feed them into `dict()` which converts the pairs into dictionary entries.

The function `insert_record_to_hosts()` first deletes old values matching that host from both the `hosts` table and the `dhcp4_options` table. It inserts the new parameters into the `hosts` table. It then retrieves the host id that was auto assigned to the new entry, using the SQL query `SELECT LAST_INSERT_ID()`. The options are then populated into the options table using the same host id.

Two additional utility functions are provided to print the content of the two MySQL tables.

#### 3.3 Complete listing of the code to populate the dhcp host reservation parameters in the MySQL database

```python
#!/usr/bin/python

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

  # ======================================================================
  @staticmethod
  def mac2int(mac):
  # ======================================================================
    return int(mac.replace(':', ''),16)

  # ======================================================================
  @staticmethod
  def int2mac(i):
  # ======================================================================
    if type(i) == str:
      i = int(i, 16)
    s = hex(i).strip('0x').zfill(12)
    s = re.sub(r'(..)(?=[^$])', r'\1:', s)
    return s

  # ======================================================================
  @staticmethod
  def ip2int(ip):
  # ======================================================================
    return int(ipaddress.ip_address(ip))

  # ======================================================================
  @staticmethod
  def int2ip(i):
  # ======================================================================
    return str(ipaddress.ip_address(i))

  # ======================================================================
  @staticmethod
  def ip2hex(ip):
  # ======================================================================
    return hex(int(ipaddress.ip_address(ip))).strip('0x').zfill(8)

  # ======================================================================
  @staticmethod
  def ip_list2hex(ip_list):
  # ======================================================================
    return ''.join(map(kea_db.ip2hex, ip_list))

  # ======================================================================
  @staticmethod
  def hex_2ip_list(h):
  # ======================================================================
    return map(lambda t: str(ipaddress.ip_address(int(t, 16))), h)

  # ======================================================================
  def getHostId(self, mac_address):
  # ======================================================================
    self.mycursor.execute(f"""select host_id from hosts 
                  where dhcp_identifier =
                   UNHEX('{mac_address.replace(':', '')}');""")
    return self.mycursor.fetchall()

  # ======================================================================
  def delete_from_database(self, mac_address):
  # ======================================================================
    hosts_id = self.getHostId(mac_address)
    for host_id in [t[0] for t in hosts_id]:
      self.mycursor.execute(f"delete from dhcp4_options where host_id={host_id};")
      self.mycursor.execute(f"delete from dhcp6_options where host_id={host_id};")
      self.mycursor.execute(f"delete from hosts     where host_id={host_id};")
    self.mydb.commit()

  # ======================================================================
  def insert_record_to_hosts(self, mac_address, identifier_type, dhcp4_subnet_id, ipv4_address, host_name):
  # ======================================================================
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

  # ======================================================================
  def set_option(self, host_id, option, value, scope_name='subnet'):
  # ======================================================================
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

  # ======================================================================
  def print_host_database(self):
  # ======================================================================
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

  # ======================================================================
  def print_option_database(self):
  # ======================================================================
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

  # ======================================================================
  def open_database(self):
  # ======================================================================
      with open(os.path.join(os.path.dirname(__file__), "db.yaml"), 'r') as f:
          conf = yaml.load(f, Loader=yaml.BaseLoader)
      db_conf = conf['db']
      self.mydb = mysql.connector.connect(**db_conf)

  # ======================================================================
  def copy_csv_to_db(self, csv_file_name):
  # ======================================================================
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


```

##### 4. Installation

The code is available at <git@github.com:josh73/migrate-host-reservations-to-kea-mysql.git>. Clone the repository and edit the file db.yaml to update the host address of your MySQL server and the password to the kea user on the kea database.

##### 5. Conclusion

I was able to use this Python code to convert my old isc-dhcp-server host reservation database to Kea with a MySQL back-end. The next step is to add IPv6 support. I will be happy to publish follow-on tutorials on these topics if there is an interest.


##### 6. References

1.  https://en.wikipedia.org/wiki/Dynamic_Host_Configuration_Protocol) 
2.  https://en.wikipedia.org/wiki/Comparison_of_DHCP_server_software) 
3.  https://downloads.isc.org/isc/kea/cur/doc/kea-guide.html#ipv4-subnet-id 
4.  https://www.iana.org/assignments/bootp-dhcp-parameters/bootp-dhcp-parameters.txt 
5.  https://docs.infoblox.com/display/NAG8/About+IPv4+DHCP+Options
6.  https://downloads.isc.org/isc/kea/cur/doc/kea-guide.html#dhcp4-std-options
7.  https://oldkea.isc.org/wiki/HostReservationsHowTo
8.  https://gitlab.isc.org/isc-projects/kea/wikis/docs/editing-host-reservations
9.  http://www.lillyrnd.com/index.php/kea-dhcp-server/
10. <git@github.com:josh73/migrate-host-reservations-to-kea-mysql.git>

