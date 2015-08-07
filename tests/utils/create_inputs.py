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
            f.write("image: '%s'\n" % image)
            f.write("flavor: '%s'\n" % flavor)
            f.write("agent_user: '%s'\n" % agent_user)


if __name__ == '__main__':
    main(*sys.argv[1:])
