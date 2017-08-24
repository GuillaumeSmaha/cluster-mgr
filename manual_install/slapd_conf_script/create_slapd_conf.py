import ConfigParser, os

cur_dir=os.path.dirname(os.path.abspath(__file__))
print cur_dir

config = ConfigParser.ConfigParser()
config.readfp(open('syncrepl.cfg'))


syncrepl_temp = open(os.path.join(cur_dir, "ldap_templates", "syncrepl.temp")).read()



def get_slappass(psw):

    crypted = os.popen("/opt/symas/bin/slappasswd -s {}".format(psw)).read()
    return crypted[:-1]


ldp_servers = []

s_id = 1
for ldp in config.sections():


    if config.get(ldp, 'enable').lower() in ('yes', 'true', 'on', '1'):

        ldp_servers.append( {
            'id': s_id,
            'fqn_hostname':    config.get(ldp, 'fqn_hostname'),
            'ldap_password': config.get(ldp, 'ldap_password'),
               })
        s_id +=1

for ldp in ldp_servers:
    cur_ldp = ldp
    slapd_tmp=open(os.path.join(cur_dir, "ldap_templates", "slapd.conf")).read()
    repls=''
    rootpwd = get_slappass(ldp['ldap_password'])


    slapd_tmp = slapd_tmp.replace('{#ROOTPW#}', rootpwd)
    slapd_tmp = slapd_tmp.replace('{#SERVER_ID#}', str(ldp['id']))


    for ldpc in ldp_servers:
        if ldpc == ldp:
            pass
        else:
            provider_id = str(ldpc['id']).zfill(3)
            repls_tmp = syncrepl_temp.replace('{#PROVIDER_ID#}', provider_id)
            repls_tmp = repls_tmp.replace('{#PROVIDER_PWD#}', ldpc['ldap_password'])
            repls_tmp = repls_tmp.replace('{#PROVIDER_ADDR#}', ldpc['fqn_hostname'])


            repls += repls_tmp

    slapd_tmp = slapd_tmp.replace('{#SYNCREPL#}', repls)

    with open(os.path.join(cur_dir + '/{}.conf'.format(ldp['fqn_hostname'].replace('.','_'))),'w') as f:
        f.write(slapd_tmp)
