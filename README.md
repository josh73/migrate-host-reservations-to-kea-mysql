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

