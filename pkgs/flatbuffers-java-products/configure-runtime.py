# SPDX-License-Identifier: MIT
"""Configure the native bundle backend's reproducible-build instructions."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

path=Path(sys.argv[1]);original=path.read_bytes();(path.parent/'sdk-original.pom').write_bytes(original)
NS='http://maven.apache.org/POM/4.0.0';q=lambda name:'{'+NS+'}'+name
ET.register_namespace('',NS);ET.register_namespace('xsi','http://www.w3.org/2001/XMLSchema-instance')
tree=ET.parse(path);root=tree.getroot();plugins=[node for node in root.findall('./'+q('build')+'/'+q('plugins')+'/'+q('plugin')) if node.findtext(q('artifactId'))=='maven-bundle-plugin']
if len(plugins)!=1:raise ValueError('native SDK must declare one bundle backend')
plugin=plugins[0];configuration=plugin.find(q('configuration'))
if configuration is None:configuration=ET.SubElement(plugin,q('configuration'))
instructions=configuration.find(q('instructions'))
if instructions is None:instructions=ET.SubElement(configuration,q('instructions'))
for key in ['_reproducible','_noextraheaders']:
 node=instructions.find(q(key))
 if node is not None and node.text!='true':raise ValueError('native SDK has conflicting bundle instruction: '+key)
 if node is None:ET.SubElement(instructions,q(key)).text='true'
tree.write(path,encoding='utf-8',xml_declaration=True)
