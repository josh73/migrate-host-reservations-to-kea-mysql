#!/home/josh/anaconda3/bin/python
import sys, os
import re
import csv

# ===========================================================================
def extract_reservation_params(t):
# ===========================================================================
    hostname, items = t
    mac           = re.search(r'hardware ethernet\s+(.+?);', items).groups()[0]
    ipv4_address  = re.search(r'fixed-address\s+(.+?);', items).groups()[0]
    other_options = re.findall(r'.+?option (\S+)\s+(\S+);', items, re.DOTALL)
    return hostname, mac, ipv4_address, other_options

# ===========================================================================
def main():
# ===========================================================================
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

# ===========================================================================
if __name__ == '__main__':
  main()

