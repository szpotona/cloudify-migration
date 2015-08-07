import sys, requests
from cloudify_cli import utils


def main(deployment_id):
    management_ip = utils.get_management_server_ip()
    client = utils.get_rest_client(management_ip)
    outputs_resp = client.deployments.outputs.get(deployment_id)
    endpoint = outputs_resp.outputs['endpoint']

    # Making sure that Nodecellar works
    response = requests.get(
        'http://{0}:{1}'.format(endpoint["ip_address"], endpoint["port"])
    )
    assert 200 == response.status_code, "Nodecellar is not up.."


if __name__ == '__main__':
    main(*sys.argv[1:])

