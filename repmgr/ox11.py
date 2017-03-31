import requests

GENERATE_KEY_ENDPOINT = '/oxeleven/rest/oxeleven/generateKey'
DELETE_KEY_ENDPOINT = '/oxeleven/rest/oxeleven/deleteKey'

def generate_key(ox11server='http://localhost:8190', signature_algorithm='RS512', expiration_time='216000', token='d-u-m-m-y'):
    url = ox11server + GENERATE_KEY_ENDPOINT
    payload = {'signatureAlgorithm': signature_algorithm, 'expirationTime': expiration_time}
    headers = {'Authorization': 'Bearer {}'.format(token)}
    r = requests.post(url, data=payload, headers=headers, verify=False)
    return r.json()

def delete_key(ox11server='http://localhost:8190', kid='d-u-m-m-y', token='d-u-m-m-y'):
    url = ox11server + DELETE_KEY_ENDPOINT
    payload = {'kid': kid}
    headers = {'Authorization': 'Bearer {}'.format(token)}
    r = requests.post(url, data=payload, headers=headers, verify=False)
    return r.json()
