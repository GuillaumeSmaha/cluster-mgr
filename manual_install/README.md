Steps for manual integration of delt-syncrepl with Gluu
=======================
#### (Only tested with Ubuntu 14 Trusty, but the process shouldn't be OS specific.)

### 1) [Install Gluu](https://gluu.org/docs/ce/3.0.2/installation-guide/install/) on one server using a separate NGINX server FQDN as hostname. 
- This is required since replicating a Gluu server to a different hostname breaks the functionality of OxTrust and OxAuth when using a hostname other than what is in the certificates. For example, if I used c1.gluu.info as my host and another install of gluu as c2.gluu.info, the process of accessing the site on c2.gluu.info, even with replication, will fail authentication. So if c1 failed, you couldn't access the Gluu web GUI anymore.

### 2) Copy the installation properties to the new servers.

```
scp /install/community-edition-setup/setup.properties.last root@server.com:/opt/gluu-server-3.0.2/install/community-edition-setup/
```

- Edit the IP address in the file to the servers actual IP address. The entry will begin with `ip=` and is usually on the 175th line. 

- Then rename to setup.properties

`mv setup.properties.last setup.properties`

### 4) Run `setup.py` and just hit `enter`. The configuration's are already loaded.

### 5) There needs to be primary server to replicate from initially for delta-syncrepl to inject data from. After the initial sync, all servers will be exactly the same. 

- So choose one server as a base and then on every other server:
```
rm /opt/gluu/data/main_db/*.mdb
```
- now make accesslog directories on every servers
```
mkdir /opt/gluu/data/accesslog_db
chown -r .ldap /opt/gluu/data/
```
### 6) Now is where we will set servers to associate with each other for MMR by editing the slapd.conf, ldap.conf and symas-openldap.conf files.

- Creating the slapd.conf file is relatively easy, but can be prone to errors if done manually. Attached is are a script and template files for creating multiple slapd.conf files for every server. Download git and the necessary files:
```
# apt-get update && apt-get install git && cd /tmp/ && git clone https://github.com/GluuFederation/cluster-mgr.git && cd /tmp/cluster-mgr/manual_install/slapd_conf_script/
```
- We need to configure the file for our own specific needs:
```
vi syncrepl.cfg
```
- Here we want to change the `ip_address`, `fqn_hostname`, `ldap_password` to our specific server instances. For example:
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
- The hostname should be the FQDN of the servers, not the NGINX server.

- If required, you can change the `/tmp/cluster-mgr/manual_install/slapd_conf_script/ldap_templates/slapd.conf` to fit your specific needs to include different schemas, indexes, etc. Avoid changing any of the `{#variables#}`.

- Now run the python script `create_slapd_conf.py`:
```
# python /tmp/cluster-mgr/manual_install/slapd_conf_script/create_slapd_conf.py
```
- This will output multiple `.conf` files in your current directory named to match your server FQDN:
```
# ls
... server1_com.conf  server2_com.conf ...
```
- Move each .conf file to their respective server @:
`/opt/gluu-server-3.0.2/opt/symas/etc/openldap/slapd.conf`
- Now create and modify the ldap.conf:
```
vi /opt/symas/etc/openldap/ldap.conf
```
- Add these lines
```
TLS_CACERT /etc/certs/openldap.pem
TLS_REQCERT never
``` 
- Modify the HOST_LIST entry of symas-openldap.conf:
```
vi /opt/symas/etc/openldap/symas-openldap.conf
```
- Edit like so:
```
...
HOST_LIST="ldaps://0.0.0.0:1636/ ldaps:///"
...
```
### 7) It is important that our servers times are synchronized so we must install ntp outside of the Gluu chroot and set ntp to update by the minute (necessary for delta-sync log synchronization). If time gets out of sync, the entries will conflict and their could be issues.
```
GLUU.root@host:/ # logout
# apt install ntp
# crontab -e
```
- Select your preferred editor and add this to the bottom of the file:
```
* * * * * /usr/sbin/ntpdate -s time.nist.gov
```
- This synchronizes the time every minute.

### 8) Force-reload solserver on every server
```
# service gluu-server-3.0.2 login
# service solserver force-reload
```
### 8) Delta-sync multi-master replication should be initializing and running. Check the logs for confirmation. It might take a moment for them to sync, but you should end up see something like the following:

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

### 9) Configuring your NGINX server is simple enough. 
- We need the httpd.crt and httpd.key certs from our base Gluu installation.
```
mkdir /etc/nginx/ssl/
scp root@server1.com:/opt/gluu-server-3.0.2/etc/certs/httpd.*
```
- Next we configure NGINX to proxy-pass connections.
```
apt-get install nginx -y
cd /etc/nginx/
>nginx.conf
vi nginx.conf
```
- Put this template in it's place. Make sure to change the `{serverX_ip_or_FQDN}` portion to your servers IP addresses or FQDN under the upstream section. Add as many servers as exister in your replication setup. The `server_name` needs to be your NGINX servers FQDN.
```
user www-data;
worker_processes 4;
pid /run/nginx.pid;

events {
        worker_connections 768;
        # multi_accept on;
}

http {
  upstream backend_id {
    ip_hash;
    server {server1_ip_or_FQDN}:443;
    server {server2_ip_or_FQDN}:443;
  }

  server {
    listen 80;
    listen 443;
    server_name {NGINX_server_FQDN};

    ssl on;
    ssl_certificate         /etc/nginx/ssl/httpd.crt;
    ssl_certificate_key     /etc/nginx/ssl/httpd.key;

    location ~ ^(/)$ {
      proxy_pass https://backend_id;
    }
    location /oxauth {
        proxy_pass https://backend_id/oxauth;
    }

    location /idp {
        proxy_pass https://backend_id/idp;
    }
    location /identity {
        proxy_pass https://backend_id/identity;
    }
  }
}

```
- Now all traffic for the Gluu web GUI will route through one address i.e. nginx.gluu.info. This gives us fail-over redunancy for our Gluu web GUI if any server goes down, as NGINX automatically does passive health checks.


### If you have any questions, please make a post on the community support.gluu.org website, and we will assist you.

