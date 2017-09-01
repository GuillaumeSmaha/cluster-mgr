from paramiko.client import SSHClient, AutoAddPolicy


class ClientNotSetupException(Exception):
    """Exception raised when the client is not initialized because
    of connection failures."""
    pass


class RemoteClient(object):
    """Remote Client is a wrapper over SSHClient with utility functions.

    Args:
        host (string): The hostname of the server to connect. It can be an IP
            address of the server also.
        user (string, optional): The user to connect to the remote server. It
            defaults to root

    Attributes:
        host (string): The hostname passed in as a the argument
        user (string): The user to connect as to the remote server
        client (:class:`paramiko.client.SSHClient`): The SSHClient object used
            for all the communications with the remote server.
        sftpclient (:class:`paramiko.sftp_client.SFTPClient`): The SFTP object
            for all the file transfer operations over the SSH.
    """

    def __init__(self, host, user='root'):
        self.host = host
        self.user = user
        self.client = SSHClient()
        self.sftpclient = None
        self.client.set_missing_host_key_policy(AutoAddPolicy())
        self.client.load_system_host_keys()

    def startup(self):
        """Function that starts SSH connection and makes client available for
        carrying out the functions.
        """
        self.client.connect(self.host, port=22, username=self.user)
        self.sftpclient = self.client.open_sftp()

    def download(self, remote, local):
        """Downloads a file from remote server to the local system.

        Args:
            remote (string): location of the file in remote server
            local (string): path where the file should be saved
        """
        if not self.sftpclient:
            raise ClientNotSetupException(
                'Cannot download file. Client not initialized')

        return self.sftpclient.get(remote, local)

    def upload(self, local, remote):
        """Uploads the file from local location to remote server.

        Args:
            local (string): path of the local file to upload
            remote (string): location on remote server to put the file
        """
        if not self.sftpclient:
            raise ClientNotSetupException(
                'Cannot upload file. Client not initialized')

        return self.sftpclient.put(local, remote)

    def exists(self, filepath):
        """Returns whether a file exists or not in the remote server.

        Args:
            filepath (string): path to the file to check for existance

        Returns:
            True if it exists, False if it doesn't
        """
        if not self.client:
            raise ClientNotSetupException(
                'Cannot run procedure. Client not initialized')
        cin, cout, cerr = self.client.exec_command('stat {0}'.format(filepath))
        if len(cout.read()) > 5:
            return True
        elif len(cerr.read()) > 5:
            return False

    def run(self, command):
        """Run a command in the remote server.

        Args:
            command (string): the command to be run on the remote server
        """
        if not self.client:
            raise ClientNotSetupException(
                'Cannot run procedure. Client not initialized')

        return self.client.exec_command(command)

    def close(self):
        """Close the SSH Connection
        """
        self.client.close()
