import functools
import logging
import os

from django import template
from django.conf import settings
from django.template import loader
from django.db.models import signals
import paramiko

from djeep.rolemapper import models

# I handle writing the files to disk that need to be kept in sync with our db


logging = logging.getLogger(__name__)


def _ensure_dir(d):
  try:
    os.makedirs(d)
    logging.info('Created directory: %s', d)
  except os.error:
    pass


def _write_pxelinux(outdir=settings.PXELINUX):
  _ensure_dir(outdir)
  templatevars = models.TemplateVar.objects.all()
  site = dict((x.key, x.value) for x in templatevars)
  # TODO(termie): clear out old files

  for host in models.HardwareInfo.objects.all():
    pxeconfig = host.kick_target.pxeconfig

    c = template.Context(locals())
    t = loader.get_template(os.path.join('pxeconfig', pxeconfig))
    outfile = '01-%s' % (host.mac_address.replace(':', '-').lower())
    with open('%s/%s' % (outdir, outfile), 'w') as out:
      out.write(t.render(c))
      logging.info('Wrote PXE for: %s', host.hostname)


def _write_dnsmasq_conf(outdir=settings.ETC):
  _ensure_dir(outdir)
  templatevars = models.TemplateVar.objects.all()
  site = dict((x.key, x.value) for x in templatevars)
  tftproot = settings.TFTPROOT

  c = template.Context(locals())
  t = loader.get_template(os.path.join('etc', 'dnsmasq.conf'))
  outfile = os.path.join(outdir, 'dnsmasq.conf')
  with open(outfile, 'w') as out:
    out.write(t.render(c))
    logging.info('Wrote etc/dnsmasq.conf')


def _write_dnsmasq_ethers(outdir=settings.ETC):
  _ensure_dir(outdir)
  templatevars = models.TemplateVar.objects.all()
  site = dict((x.key, x.value) for x in templatevars)
  hosts = models.HardwareInfo.objects.all()

  c = template.Context(locals())
  t = loader.get_template(os.path.join('etc', 'ethers'))
  outfile = os.path.join(outdir, 'ethers')
  with open(outfile, 'w') as out:
    out.write(t.render(c))
    logging.info('Wrote etc/ethers')


def _write_dnsmasq_hosts(outdir=settings.ETC):
  _ensure_dir(outdir)
  templatevars = models.TemplateVar.objects.all()
  site = dict((x.key, x.value) for x in templatevars)
  hosts = models.HardwareInfo.objects.all()

  c = template.Context(locals())
  t = loader.get_template(os.path.join('etc', 'hosts'))
  outfile = os.path.join(outdir, 'hosts')
  with open(outfile, 'w') as out:
    out.write(t.render(c))
    logging.info('Wrote etc/hosts')


def _write_ssh_key(outdir=settings.SSH):
  _ensure_dir(outdir)
  outfile = os.path.join(outdir, 'id_rsa')
  outfile_public = os.path.join(outdir, 'id_rsa.pub')

  if not os.path.exists(outfile):
    private = paramiko.RSAKey.generate(1024)
    private.write_private_key_file(outfile)
    logging.info('Wrote ssh/id_rsa')
  else:
    private = paramiko.RSAKey.from_private_key_file(outfile)

  if not os.path.exists(outfile_public):
    with open(outfile_public, 'w') as out:
      out.write('%s %s' % (private.get_name(), private.get_base64()))
      logging.info('Wrote ssh/id_rsa.pub')


def _write_authorized_keys(outdir=settings.SSH):
  public_key_path = os.path.join(outdir, 'id_rsa.pub')
  public_key = open(public_key_path).read()
  command = '/sbin/shutdown -rf now'
  outfile = os.path.join(outdir, 'authorized_keys')

  if not os.path.exists(outfile):
    with open(outfile, 'w') as out:
      out.write('command="%s" %s' % (command, public_key))
      logging.info('Wrote ssh/authorized_keys')


def sync_to_disk(sender=None, *args, **kwargs):
  """Do the work to make sure our changes are synced to disk."""
  updating_models = (models.TemplateVar,
                     models.HadrwareInfo,
                     models.Cluster,
                     models.KickTarget)

  if sender and sender not in updating_models:
    return
  _write_pxelinux()
  _write_dnsmasq_conf()
  _write_dnsmasq_ethers()
  _write_dnsmasq_hosts()
  _write_ssh_key()
  _write_authorized_keys()


signals.post_save.connect(sync_to_disk)
signals.post_delete.connect(sync_to_disk)
