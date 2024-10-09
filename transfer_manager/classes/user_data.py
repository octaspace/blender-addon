class UserData:
    def __init__(self, farm_host, api_token, qm_auth_token):
        self.farm_host = farm_host  # host of the private farm
        self.api_token = api_token  # api token to talk to cube and r2 worker
        self.qm_auth_token = qm_auth_token  # auth token used by the sarfis qm

    def to_dict(self):
        return {
            'farm_host': self.farm_host,
            'api_token': self.api_token[:10] + "...",
            'qm_auth_token': self.qm_auth_token[:10] + "...",
        }
