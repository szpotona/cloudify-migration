import sys, os


def main(output_f, image, flavor, agent_user):
    with open(output_f, 'w') as f:
        if os.environ['OLD_MANAGER_VER'] == "3.1":
            import json
            f.write(json.dumps({
                'image': image,
                'flavor': flavor,
                'agent_user': agent_user
            }))
        else:
            f.write("image: '%s'" % image)
            f.write("flavor: '%s'" % flavor)
            f.write("agent_user: '%s'" % agent_user)


if __name__ == '__main__':
    main(*sys.argv[1:])
