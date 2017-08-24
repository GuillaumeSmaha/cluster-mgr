Steps for manual integration of delt-syncrepl with Gluu
=======================

### 1. [Install Gluu](https://gluu.org/docs/ce/3.0.2/installation-guide/install/) on all servers. Make sure you remember or have access to the LDAP password you set here.
### 2. After install and setup, log in to the Gluu chroot
```
service gluu-server-3.0.2 login
```
### 3. Provided are a script, configuration and template files to automatically create slapd.conf files for each server. We will download it from Github and then modify the configuration files for each server.

Download and using git inside the Gluu chroot:
```
# apt-get update && apt-get install git && cd /tmp/ && git clone https://github.com/GluuFederation/cluster-mgr.git && cd /tmp/cluster-mgr/manual_install/slapd_conf_script/
```
OR each file individually:
```
# cd /tmp/ && mkdir /tmp/slap_script/ && mkdir /tmp/slap_script/ldap_templates && cd /tmp/slap_script/ && wget https://raw.githubusercontent.com/GluuFederation/cluster-mgr/master/manual_install/slapd_conf_script/create_slapd_conf.py &&  wget https://raw.githubusercontent.com/GluuFederation/cluster-mgr/master/manual_install/slapd_conf_script/syncrepl.cfg && cd ldap_templates && wget https://raw.githubusercontent.com/GluuFederation/cluster-mgr/master/manual_install/slapd_conf_script/ldap_templates/slapd.conf && wget https://raw.githubusercontent.com/GluuFederation/cluster-mgr/master/manual_install/slapd_conf_script/ldap_templates/syncrepl.temp && cd ..
```
### 4. We now have to modify the `syncrepl.cfg` file in our current directory */tmp/cluster-mgr/manual_install/slapd_conf_script*:
```
# vi syncrepl.cfg
```
Here we want to change the `ip_address`, `fqn_hostname`, `ldap_password` to our specific server instances. For example:
```
[server_1]
ip_address = 192.168.30.133
fqn_hostname = server1.com
ldap_password = (your password)
enable = Yes

[server_2]
ip_address = 192.168.30.130
fqn_hostname = server2.com
ldap_password = (your password)
enable = Yes

[server_3]
...
```
Add as many servers as is required. Now run the python script `create_slapd_conf.py`:
```
# python /tmp/cluster-mgr/manual_install/slapd_conf_script/create_slapd_conf.py
```
This will output multiple .conf files in your current directory matching your server FQDN
```
... server1_com.conf  server2_com.conf ...
```
Now we need to move these `*.conf` files to their appropriate servers. Having root ssh access to these servers is ideal. For the first, simply:
```
mv server1_com.conf /opt/symas/etc/openldap/slapd.conf
```
To replace the file. The others must be copied to their respective server.
```
scp server2_com.conf root@server2.com:/opt/gluu-server-3.0.2/opt/symas/etc/openldap/slapd.conf
scp server3_com.conf root@server3.com:/opt/gluu-server-3.0.2/opt/symas/etc/openldap/slapd.conf
```
Else you can scp it to 
```
root@serverX.com:/home/*login*/slapd.conf
```
And manually move it to 
```
mv /opt/gluu-server-3.0.2/opt/symas/etc/openldap/slapd.conf
```

### 5. Next is to create and modify ldap.conf in the */opt/symas/etc/openldap/* directory:
```
# vi /opt/symas/etc/openldap/ldap.conf
```Add this line```
TLS_CACERT /etc/certs/openldap.pem
``` 
#### 6. Modify the HOST_LIST entry in */opt/symas/etc/openldap/symas-openldap.conf*
```
...
HOST_LIST="ldaps://0.0.0.0:1636/ ldaps:///"
...
```
#### 7. Now if you have a primary server with a Gluu database already (if not, just pick one to be the base):
- On your new servers (**NOT YOUR 'PRIMARY' SERVER**)
```
# service solserver stop
# rm /opt/gluu/data/main_db/*.mdb
# rm /opt/gluu/data/site_db/*.mdb
```
This is necessary because each Gluu instance creates unique inum's under o=gluu, so the servers base directory techinically won't match. We delete the brand new databases and replace with our own existing database later. We will import database information shortly.

### 8. Make an accesslog database directory on every server for delta-syncrepl to write logs for entries to:
```
# mkdir /opt/gluu/data/accesslog_db
# chown -R ldap.ldap /opt/gluu/data
```
### 9. Copy the contents of */etc/gluu/conf/* from Server 1 and replace on every other server. 
##### To server2:
```
# ssh root@server2.com "rm -rf /opt/gluu-server-3.0.2/etc/gluu/conf/
# scp -r /etc/gluu/conf/ root@serverX.com:/opt/gluu-server-3.0.2/etc/gluu/
```
### 10. On your primary database server
```
# service solserver stop
# /opt/symas/bin/slapcat -l alldata.ldif
```
This pulls our database into a single `.ldif` file which we will import into our new fresh and empty Gluu servers.

#### 11. `scp` the data to the wiped servers.
##### To server 2:
```
# scp alldata.ldif root@server2:/opt/gluu-server-3.0.2/opt/symas/etc/openldap/alldata.ldif
```
for each server.

### 12. On the wiped servers:
```
# service solserver stop
# chown -R ldap.ldap /opt/gluu/data
# /opt/symas/bin/slapadd -w -s -l /opt/symas/etc/openldap/alldata.ldif
# chown -R ldap.ldap /opt/gluu/data
```
We run `chown -R` the first time to give ldap access recursively to ever directory in /opt/gluu/data. `slapadd` then injects all of our information and creates the databases in their respective directories. We then `chown -R` to make sure ldap can access them when we restart solserver.

### 13. Install ntp outside of the Gluu chroot and set ntp to update by the minute (necessary for delta-sync log synchronization). If time gets out of sync, the entries will conflict and their could be issues.

```
GLUU.root@host:/ # logout
# apt install ntp
# crontab -e
(select your preferred editor and add this to the bottom of the file)
* * * * * /usr/sbin/ntpdate -s time.nist.gov
```
This synchronizes the time every minute.

### 14. Force-reload solserver on every server
```
# service solserver force-reload
```
### 15. delta-sync multimaster replication should be initializing and running. Check the logs for confirmation. It might take a moment for them to sync, but you should end up see something like the following:
```
# tail -f /var/log/openldap/ldap.log | grep sync

Aug 23 22:40:29 dc4 slapd[79544]: do_syncrep2: rid=001 cookie=rid=001,sid=001,csn=20170823224029.216104Z#000000#001#000000
Aug 23 22:40:29 dc4 slapd[79544]: syncprov_matchops: skipping original sid 001
Aug 23 22:40:29 dc4 slapd[79544]: syncrepl_message_to_op: rid=001 be_modify inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu (0)
Aug 23 22:40:29 dc4 slapd[79544]: syncprov_sendresp: to=003, cookie=rid=002,sid=002,csn=20170823224029.216104Z#000000#001#000000
Aug 23 22:40:36 dc4 slapd[79544]: do_syncrep2: rid=001 cookie=rid=001,sid=001,csn=20170823224036.310829Z#000000#001#000000
Aug 23 22:40:36 dc4 slapd[79544]: syncprov_matchops: skipping original sid 001
Aug 23 22:40:36 dc4 slapd[79544]: syncrepl_message_to_op: rid=001 be_modify inum=@!7A50.0E96.90FB.EA93!0002!F7B4.A83E,ou=appliances,o=gluu (0)
Aug 23 22:40:36 dc4 slapd[79544]: syncprov_sendresp: to=003, cookie=rid=002,sid=002,csn=20170823224036.310829Z#000000#001#000000
```


