Steps for manual integration of delt-syncrepl with Gluu
=======================

1. [Install Gluu](https://gluu.org/docs/ce/3.0.2/installation-guide/install/) on all servers.
2. Log in to Gluu (Most actions take place inside the Gluu chroot) and run ./setup.py
3. Modify the slapd_example.conf provided for each server.

    - Make sure to change the serverid on the top of the file, starting with 1. All servers must have a different server id.
    - Provide your own passwords for each rootdn, preferably hashed in the designated locations {Your hash password here}
    - Insert a syncrepl block for each server you have (n-1). Replication ID (rid) MUST match the provider across the servers. 
    - An example for 2 servers:
  
  ### server 1
 ```
  syncrepl
  rid=002
      provider=ldaps://{Insert server FQDN here i.e. c2.gluu.org}
      tls_reqcert=never
      bindmethod=simple
      
      binddn="{Insert main_db rootdn credentials i.e. "cn=directory manager,o=gluu"}
      
      credentials={Your hash password for your bindDN}
      
      type=refreshAndPersist
      searchbase="o=gluu"
      filter="(objectclass=*)"
      scope=sub
      retry="5 10 60 +"
      logbase="cn=accesslog"
      logfilter="(&(objectClass=auditWriteObject)(reqResult=0))"
      syncdata=accesslog
      sizeLimit=unlimited
      timelimit=unlimited
```
### server 2
  ```
  syncrepl
  rid=001
      provider=ldaps://{Insert server FQDN here i.e. c1.gluu.org} 
      tls_reqcert=never
      bindmethod=simple
      
      binddn="{Insert main_db rootdn credentials i.e. "cn=directory manager,o=gluu"}
      
      credentials={Your hash password for your bindDN}
      
      type=refreshAndPersist
      searchbase="o=gluu"
      filter="(objectclass=*)"
      scope=sub
      retry="5 10 60 +"
      logbase="cn=accesslog"
      logfilter="(&(objectClass=auditWriteObject)(reqResult=0))"
      syncdata=accesslog
      sizeLimit=unlimited
      timelimit=unlimited
```
4. Replace all slapd.conf's with your individually modified slapd.conf's.

5. Create and modify ldap.conf
```
# vi /opt/symas/etc/openldap/ldap.conf
TLS_CACERT /path/to/cert.pem
```
6. Modify /opt/symas/etc/openldap/symas-openldap.conf
```
...
HOST_LIST="ldaps://0.0.0.0:1636/ ldaps:///"
...
```
7. Now if you have a primary server with a Gluu database already (if not, just pick one to be the base):
- On your new servers (**NOT YOUR 'PRIMARY' SERVER**)
```
# service solserver stop
# rm /opt/gluu/data/main_db/*.mdb
# rm /opt/gluu/data/site_db/*.mdb
```
8. Make an accesslog database directory:
```
# mkdir /opt/gluu/data/accesslog_db
```
9. Copy the contents of /etc/gluu/conf/ from Server 1 and replace on every other server. The ox-ldap.properties file is the only one that needs to change. 
    - the servers: portion must have the other servers FQDN's, excluding the server with which the .properties file resides.
    - For example:
### Server 1
```
bindDN: cn=directory manager,o=gluu
bindPassword: GOvhsv/gPvg=
servers: localhost:1636,server2.com:1636,server3.com:1636
useSSL: true
maxconnections: 10

oxauth_ConfigurationEntryDN=ou=oxauth,ou=configuration,inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu
oxtrust_ConfigurationEntryDN=ou=oxtrust,ou=configuration,inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu
oxidp_ConfigurationEntryDN=ou=oxidp,ou=configuration,inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu
oxcas_ConfigurationEntryDN=ou=oxcas,ou=configuration,inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu
oxasimba_ConfigurationEntryDN=ou=oxasimba,ou=configuration,inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu
oxpassport_ConfigurationEntryDN=ou=oxpassport,ou=configuration,inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu

certsDir=/etc/certs
confDir=
pythonModulesDir=/opt/gluu/python/libs

binaryAttributes=objectGUID
```
### Server 2
```
bindDN: cn=directory manager,o=gluu
bindPassword: GOvhsv/gPvg=
servers: localhost:1636,server1.com:1636,server3:1636
useSSL: true
maxconnections: 10

oxauth_ConfigurationEntryDN=ou=oxauth,ou=configuration,inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu
oxtrust_ConfigurationEntryDN=ou=oxtrust,ou=configuration,inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu
oxidp_ConfigurationEntryDN=ou=oxidp,ou=configuration,inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu
oxcas_ConfigurationEntryDN=ou=oxcas,ou=configuration,inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu
oxasimba_ConfigurationEntryDN=ou=oxasimba,ou=configuration,inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu
oxpassport_ConfigurationEntryDN=ou=oxpassport,ou=configuration,inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu

certsDir=/etc/certs
confDir=
pythonModulesDir=/opt/gluu/python/libs

binaryAttributes=objectGUID
```
10. On your base server
```
# service solserver stop
# /opt/symas/bin/slapcat -l alldata.ldif
```
11. scp the data to the servers with no databases
12. On the other servers
```
# service solserver force-reload
# chown -R ldap.ldap /opt/gluu/data
# service solserver force-reoad
# slapadd -w -s -l /path/to/alldata.ldif
```
13. Install ntp outside of the Gluu chroot and set ntp to update by the minute (necessary for delta-sync log synchronization)
```
# logout
# apt install ntp
# crontab -e
(select your preferred editor and add this to the bottom of the file)
* * * * * /usr/sbin/ntpdate -s time.nist.gov
```

14. Force-reload solserver on every server
```
# service solserver force-reload
```
