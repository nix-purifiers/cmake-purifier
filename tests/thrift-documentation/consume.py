# SPDX-License-Identifier: MIT
"""Exercise native documentation through HTTP, renderers and JVM resolvers."""
import functools,hashlib,http.server,json,os,re,shutil,subprocess,sys,threading,urllib.request,zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin,urlsplit,unquote
from xml.etree import ElementTree as ET

sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir();results=[]
shutil.copyfile(spec['javaConsumer'],'ResourceConsumer.java');subprocess.run(['javac','ResourceConsumer.java'],check=True);classes=str(Path.cwd())
class Links(HTMLParser):
    def __init__(self,text):
        super().__init__();self.links=[];self.ids=set();self.feed(text)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if 'id' in attrs:self.ids.add(attrs['id'])
        if tag=='a' and 'name' in attrs:self.ids.add(attrs['name'])
        for name in ['href','src']:
            if name in attrs:self.links.append(attrs[name])

def repositories(case,root,hashes):
    manifest=root/'resource-hashes.tsv';manifest.write_text(''.join(name+'\t'+digest+'\n' for name,digest in sorted(hashes.items())))
    assert subprocess.check_output(['java','-cp',classes,'ResourceConsumer',case['javaResources'],str(manifest),''],text=True).strip()==str(len(hashes))
    resolved=[]
    for kind in ['maven','ivy']:
        repo=Path(case[kind]);jars=list(repo.rglob('*.jar'));assert len(jars)==1
        if kind=='maven':
            xml=ET.parse(next(repo.rglob('*.pom'))).getroot();ns={'m':'http://maven.apache.org/POM/4.0.0'};coordinate=':'.join(xml.find('m:'+name,ns).text for name in ['groupId','artifactId','version']);config='maven { url=uri(selected.repository); metadataSources { mavenPom(); artifact() } }'
        else:
            info=ET.parse(next(repo.rglob('ivy.xml'))).getroot().find('info');coordinate=':'.join(info.attrib[name] for name in ['organisation','module','revision']);config="ivy { url=uri(selected.repository); patternLayout { ivy '[organisation]/[module]/[revision]/ivys/ivy.xml'; artifact '[organisation]/[module]/[revision]/[type]s/[artifact].[ext]' }; metadataSources { ivyDescriptor() } }"
        project=root/('gradle-'+kind);project.mkdir();(project/'settings.gradle').write_text("rootProject.name='thrift-docs-consumer'\n");(project/'config.json').write_text(json.dumps({'repository':str(repo),'coordinate':coordinate}));(project/'build.gradle').write_text("def selected=new groovy.json.JsonSlurper().parse(file('config.json'))\nrepositories { "+config+" }\nconfigurations { assets }\ndependencies { assets(selected.coordinate) }\ntasks.register('resolveAssets') { doLast { file('resolved.txt').text=configurations.assets.singleFile.canonicalPath } }\n")
        command=['gradle','--offline','--no-daemon','--console=plain','--gradle-user-home',str(root/('gradle-home-'+kind)),'resolveAssets'];run=subprocess.run(command,cwd=project,text=True,capture_output=True,timeout=180);assert run.returncode==0,(run.stdout,run.stderr)
        jar=Path((project/'resolved.txt').read_text());assert jar.read_bytes()==jars[0].read_bytes()
        with zipfile.ZipFile(jar) as archive:
            name=next(n for n in archive.namelist() if n.startswith('META-INF/resources/webjars/') and n.endswith('/html/main/index.html'));prefix=name[:-len('html/main/index.html')]
            for name,digest in hashes.items():assert hashlib.sha256(archive.read(prefix+name)).hexdigest()==digest
        assert subprocess.check_output(['java','-cp',classes,'ResourceConsumer',str(jar),str(manifest),prefix],text=True).strip()==str(len(hashes))
        resolved.append({'repository':kind,'coordinate':coordinate,'jarSha256':sha(jar),'resourceCount':len(hashes)})
    return resolved

for index,case in enumerate(spec['versions']):
    root=Path('consumer-'+str(index)).resolve();root.mkdir();docs=Path(case['generated']);web=Path(case['web']);model=json.loads((docs/'thrift-documentation.json').read_text());hashes={}
    assert len(model['products'])==10
    for record in model['products']:
        if record['target']=='json':continue
        for name,digest in record['files'].items():
            logical=record['target']+'/'+Path(record['entrypoint']).stem+'/'+name
            assert sha(web/logical)==digest;hashes[logical]=digest
    assert set(hashes)=={str(p.relative_to(web)) for p in web.rglob('*') if p.is_file()}
    assert '<td>'+str(index+1)+'</td><td>answer</td>' in (web/'html/main/value.html').read_text()
    assert 'Additional' in (web/'html/second/index.html').read_text()
    # Parse and resolve every native HTML link and fragment, not just the index.
    links=0
    for page in web.rglob('*.html'):
        for link in Links(page.read_text()).links:
            parsed=urlsplit(link);assert not parsed.scheme and not parsed.netloc,link
            target=(page.parent/unquote(parsed.path)).resolve() if parsed.path else page.resolve()
            assert target.is_relative_to(web.resolve()) and target.is_file(),(page,link)
            if parsed.fragment:assert unquote(parsed.fragment) in Links(target.read_text()).ids,(page,link)
            links+=1
    for graph in web.rglob('*.gv'):
        result=subprocess.run(['dot','-Tsvg',str(graph)],capture_output=True,check=True);svg=ET.fromstring(result.stdout);assert svg.tag.endswith('svg')
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(web)));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();browser=None
    try:
        base='http://127.0.0.1:'+str(server.server_port)+'/'
        for name,digest in hashes.items():
            with urllib.request.urlopen(base+name) as response:assert hashlib.sha256(response.read()).hexdigest()==digest
        if spec['chromium']:
            run=subprocess.run([spec['chromium'],'--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--no-first-run','--user-data-dir='+str(root/'browser-profile'),'--dump-dom',base+'html/main/main.html'],capture_output=True,text=True,timeout=45);assert run.returncode==0 and 'Struct: Envelope' in run.stdout and 'AnswerService' in run.stdout,(run.stdout,run.stderr)
            print(run.stdout,file=sys.stderr);browser={'renderedEnvelope':True,'renderedAnswerService':True}
    finally:server.shutdown();server.server_close();thread.join()
    jvm=repositories(case,root,hashes)
    results.append({'case':case,'model':model,'assetHashes':hashes,'checkedHtmlLinks':links,'httpAssetCount':len(hashes),'browser':browser,'jvm':jvm})
assert results[0]['assetHashes']!=results[1]['assetHashes']
# Rejection controls exercise original captured bytes and the native compiler.
controls=[]
for kind,expected in [('hash','captured resource hash mismatch'),('missing','Could not find include file'),('outside','native documentation input escapes captured tree'),('collision','ambiguous native documentation program'),('format','unsupported native documentation formats')]:
    root=Path('reject-'+kind).resolve();root.mkdir();bundle=root/'bundle';shutil.copytree(Path(results[0]['model']['resources']),bundle);catalog=json.loads((bundle/'catalog.json').read_text());main=bundle/'files/main.thrift';formats=['html']
    for path in [bundle,*bundle.rglob('*')]:path.chmod(path.stat().st_mode | 0o200)
    if kind=='hash':main.write_text(main.read_text()+'\n// changed source\n')
    elif kind=='missing':
        main.write_text(main.read_text().replace('common/value.thrift','absent.thrift'));catalog['files']['main.thrift']['sha256']=sha(main)
    elif kind=='outside':
        external=root/'outside.thrift';external.write_text('struct Outside { 1: i32 answer }\n');main.write_text('include '+json.dumps(str(external))+'\nstruct UsesOutside { 1: outside.Outside value }\n');catalog['files']['main.thrift']['sha256']=sha(main)
    elif kind=='collision':
        duplicate=bundle/'files/duplicate/value.thrift';duplicate.parent.mkdir();duplicate.write_bytes((bundle/'files/common/value.thrift').read_bytes());catalog['files']['duplicate/value.thrift']={'sha256':sha(duplicate)}
    else:formats=['not-a-generator']
    (bundle/'catalog.json').write_text(json.dumps(catalog));configuration=root/'spec.json';configuration.write_text(json.dumps({'resources':str(bundle),'sdk':results[0]['model']['sdk'],'formats':formats}));run=subprocess.run(['python',spec['generator'],str(configuration),str(root/'output')],capture_output=True,text=True)
    assert run.returncode!=0 and expected in run.stdout+run.stderr,(kind,run.stdout,run.stderr)
    controls.append({'control':kind,'exitCode':run.returncode,'diagnostic':expected})
(out/'verification.json').write_text(json.dumps({'consumers':results,'controls':controls},sort_keys=True,indent=2)+'\n')
