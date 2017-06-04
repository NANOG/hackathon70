#!/usr/bin/env python2.7
import pdb
import logging
import pyeapi
import argparse
from netmiko import ConnectHandler
import os
import sys
from jinja2 import Environment, FileSystemLoader
import yaml
import scp

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

TEMPLATES = { 'bb': 'TEMPLATES/vmx_template.j2',
              'spine': 'TEMPLATES/spine_template.j2',
              'leaf': 'TEMPLATES/leaf_template.j2' }

JUNOS_CONFIG_MODE_CMD = 'configure'
JUNOS_CONFIG_CLEAR_CMD = 'load factory-default'
JUNOS_CONFIG_CHECK_COMMAND = 'show | compare'
JUNOS_COMMIT_CMD = 'commit confirmed 5'
JUNOS_CONFIRM_CMD = 'commit check'
JUNOS_ROLLBACK_CMD = 'rollback 0'

class PushCore(object):


  def __init__(self, args):
    self.args = args
    self.manifest=self.get_manifest(args.manifest)

    self.env = Environment(autoescape=False,
                          loader=FileSystemLoader('./'),
                          trim_blocks=False)

  # Load YAML manifest, store as object attribute
  def get_manifest(self, manifest):
    with open(manifest) as f:
      try:
        return yaml.load(f)
      except yaml.YAMLError as exc:
        print(exc)

    # Build k/v store of hostnames to addresses, make later calls easier
    self.device_addrs = {}
    for d in self.manifest['devices']:
      self.device_addrs[d['name']] = d['address']


  def transfer_file(self, file_path, remote_host):
    remote_addr = self.device_addrs[remote_host]
    user = self.manifest['lab_user']
    password = self.manifest['lab_password']

    client = scp.Client(host=remote_addr, user=user, password=password)
    try:
      client.transfer(file_path, '/var/tmp/{}.conf'.format(remote_host))
    except Exception, e:
      print "Error transfering file: {}".format(e)
      sys.exit(1)


  def ssh_connect(self, device):
    remote_addr = device['address']
    user = self.manifest['lab_user']
    password = self.manifest['lab_password']
    
    try:
      conn = ConnectHandler(device_type='juniper', ip=remote_addr,
                            username=user, password=password) 
      return conn
    except Exception, e:
      print "Error connecting to {}: {}".format(device['name', e])
      sys.exit(1)

  def ssh_command(self, conn, command):
    print "Entering command: {}".format(command)
    try:
      #pdb.set_trace()
      print "Looking for prompt: {}".format(conn.find_prompt())
      out = conn.send_command(command)
    except Exception, e:
      print "Error executing command {}: {}".format(command, e)
      sys.exit(1)

    return out

  def generate_config(self, template_file, host_file):
    with open(host_file) as f:
      try:
        context = yaml.load(f)
      except yaml.YAMLError as exc:
        print(exc)

    template = self.env.get_template(template_file)
    return template.render(context).splitlines()
  
  def execute(self):
    # Read through each device, generate config, and push
    for device in self.manifest['devices']:
      # generate config
      conf = self.generate_config(TEMPLATES[device['role']],
                                  "YAML/{}.yaml".format(device['name']))

      # Now pass to config pusher
      self.push_config(device, conf)

  def push_config(self, device, conf):
    if device['type'] == 'junos':
      self.push_junos_config(device, conf)
    elif device['type'] == 'eos':
      self.push_eos_config(device, conf)

  def push_junos_config(self, device, conf):
    conn = self.ssh_connect(device)
    # Then send commands
    # Enter confid mode
    # pdb.set_trace()
    print self.ssh_command(conn, JUNOS_CONFIG_MODE_CMD) 
    print self.ssh_command(conn, JUNOS_CONFIG_CLEAR_CMD)

    # Load configuration
    for line in conf:
      print self.ssh_command(conn, line)

    # Show compare then check
    print self.ssh_command(conn, JUNOS_CONFIG_CHECK_COMMAND)

    # Get OK from user, then commit
    confirm = raw_input("OK to commit (y/n)? ")
    if confirm == 'y':
      print self.ssh_command(conn, JUNOS_COMMIT_CMD)
      sys.sleep(5)
      print self.ssh_command(conn, JUNOS_CONFIRM_CMD)
      print self.ssh_command(conn, 'exit')
      conn.close()

    else:
      print "Aborting."
      print self.ssh_command(conn, JUNOS_ROLLBACK_CMD)
      print self.ssh_command(conn, 'exit')
      conn.close()

      sys.exit(1)

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--manifest", type=str, required=True)
  args = parser.parse_args()  

  core = PushCore(args)
  core.execute()

if __name__ == '__main__':
  main()

