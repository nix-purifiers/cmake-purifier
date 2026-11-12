# SPDX-License-Identifier: MIT
"""Consume the browser bundle over HTTP and through real JVM repositories."""
import functools,hashlib,http.server,json,subprocess,threading,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

def verify(spec,case,model,root,wire,env,classes):
    browser=model['browser'];assert browser is not None
    source=Path(case['generated'])/'package/browser/schemas.mjs';web=Path(case['web'])
    assert source.read_bytes()==(web/'schemas.mjs').read_bytes()
    assert hashlib.sha256(source.read_bytes()).hexdigest()==browser['files']['schemas.mjs']
    for value in browser['inputHashes'].values():
        assert hashlib.sha256(Path(value['retained']).read_bytes()).hexdigest()==value['sha256']
    (root/'browser-consumer.mts').write_text('import {schema, common, Buffer, runtime} from "@proof/thrift-schemas/browser"; const value:number=new schema.Envelope({value:new common.Value({answer:42})}).value.answer; // @ts-expect-error browser runtime does not provide Node socket connections\nruntime.createConnection("localhost",9090); const bytes:Buffer=Buffer.from([value]); const protocol:typeof runtime.TBinaryProtocol=runtime.TBinaryProtocol; console.log(bytes,protocol);\n')
    typed=subprocess.run(['tsc','--strict','--target','es2020','--module','nodenext','--moduleResolution','nodenext','--noEmit','browser-consumer.mts'],cwd=root,env=env,text=True,capture_output=True)
    assert typed.returncode!=0 and 'TS1479' in typed.stdout and 'uuid' in typed.stdout,(typed.stdout,typed.stderr)
    node_next_diagnostic=typed.stdout
    typed=subprocess.run(['tsc','--strict','--target','es2020','--module','esnext','--moduleResolution','bundler','--noEmit','browser-consumer.mts'],cwd=root,env=env,text=True,capture_output=True)
    assert typed.returncode==0,(typed.stdout,typed.stderr)
    site=root/'site';site.mkdir();(site/'schemas.mjs').write_bytes(source.read_bytes())
    html='''<p id="result">pending</p><script type="module">
import {schema,common,runtime,Buffer,a,b,rpc} from './schemas.mjs';
const expected=WIRE;let decoded;
runtime.TBufferedTransport.receiver(t=>{decoded=new schema.Envelope();decoded[Symbol.for('read')](new runtime.TBinaryProtocol(t));})(Buffer.from(expected,'hex'));
if(decoded.value.answer!==42)throw Error('browser decode');let encoded;
const t=new runtime.TBufferedTransport(undefined,bytes=>encoded=bytes);new schema.Envelope({value:new common.Value({answer:42})})[Symbol.for('write')](new runtime.TBinaryProtocol(t));t.flush();
if(encoded.toString('hex')!==expected||new a.Value({answer:7}).answer!==7||new b.Value({answer:8}).answer!==8)throw Error('browser wire');const connection=runtime.createXHRConnection('127.0.0.1',RPCPORT,{path:'/rpc',transport:runtime.TBufferedTransport,protocol:runtime.TBinaryProtocol});const client=runtime.createXHRClient(rpc,connection);if(await client.answer(1)!==43)throw Error('browser RPC');document.getElementById('result').textContent='43:42:7:8:'+encoded.toString('hex');
</script>'''.replace('WIRE',json.dumps(wire));(site/'index.html').write_text(html)
    dom=None
    if spec['chromium']:
        server_script=root/'browser-rpc.cjs';server_script.write_text("const thrift=require('thrift'),service=require('@proof/thrift-schemas').rpc;const server=thrift.createWebServer({cors:{'*':true},services:{'/rpc':{processor:service,handler:{answer(delta){return 42+delta;}},transport:thrift.TBufferedTransport,protocol:thrift.TBinaryProtocol}}});server.listen(0,'127.0.0.1',()=>console.log(server.address().port));")
        rpc_server=subprocess.Popen(['node',str(server_script)],cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        port=int(rpc_server.stdout.readline().strip());(site/'index.html').write_text(html.replace('RPCPORT',str(port)))
        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(site)));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            result=subprocess.run([spec['chromium'],'--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--disable-background-networking','--no-first-run','--disable-extensions','--user-data-dir='+str(root/'browser-profile'),'--virtual-time-budget=3000','--dump-dom','http://127.0.0.1:'+str(server.server_port)+'/index.html'],capture_output=True,text=True,timeout=45)
            assert result.returncode==0 and 'id="result">43:42:7:8:'+wire in result.stdout,(result.stdout,result.stderr)
            dom=result.stdout
        finally:
            server.shutdown();server.server_close();thread.join();rpc_server.terminate();rpc_server.communicate(timeout=10)
    digest=hashlib.sha256(source.read_bytes()).hexdigest();manifest=root/'resource-hashes.tsv';manifest.write_text('schemas.mjs\t'+digest+'\n')
    assert subprocess.check_output(['java','-cp',classes,'ResourceConsumer',case['javaResources'],str(manifest),''],text=True).strip()=='1'
    resolved=[]
    for kind in ['maven','ivy']:
        repo=Path(case[kind]);jars=list(repo.rglob('*.jar'));assert len(jars)==1
        if kind=='maven':
            xml=ET.parse(next(repo.rglob('*.pom'))).getroot();ns={'m':'http://maven.apache.org/POM/4.0.0'};coordinate=':'.join(xml.find('m:'+name,ns).text for name in ['groupId','artifactId','version']);config='maven { url=uri(selected.repository); metadataSources { mavenPom(); artifact() } }'
        else:
            info=ET.parse(next(repo.rglob('ivy.xml'))).getroot().find('info');coordinate=':'.join(info.attrib[name] for name in ['organisation','module','revision']);config="ivy { url=uri(selected.repository); patternLayout { ivy '[organisation]/[module]/[revision]/ivys/ivy.xml'; artifact '[organisation]/[module]/[revision]/[type]s/[artifact].[ext]' }; metadataSources { ivyDescriptor() } }"
        project=root/('gradle-'+kind);project.mkdir();(project/'settings.gradle').write_text("rootProject.name='thrift-browser-resources'\n");(project/'config.json').write_text(json.dumps({'repository':str(repo),'coordinate':coordinate}));(project/'build.gradle').write_text("def selected=new groovy.json.JsonSlurper().parse(file('config.json'))\nrepositories { "+config+" }\nconfigurations { assets }\ndependencies { assets(selected.coordinate) }\ntasks.register('resolveAssets') { doLast { file('resolved.txt').text=configurations.assets.singleFile.canonicalPath } }\n")
        command=['gradle','--offline','--no-daemon','--console=plain','--gradle-user-home',str(root/('gradle-home-'+kind)),'resolveAssets'];run=subprocess.run(command,cwd=project,env=env,text=True,capture_output=True,timeout=180);assert run.returncode==0,(run.stdout,run.stderr)
        jar=Path((project/'resolved.txt').read_text());assert jar.read_bytes()==jars[0].read_bytes()
        with zipfile.ZipFile(jar) as archive:
            names=[name for name in archive.namelist() if name.startswith('META-INF/resources/webjars/') and name.endswith('/schemas.mjs')];assert len(names)==1 and archive.read(names[0])==source.read_bytes();prefix=names[0][:-len('schemas.mjs')]
        assert subprocess.check_output(['java','-cp',classes,'ResourceConsumer',str(jar),str(manifest),prefix],text=True).strip()=='1'
        resolved.append({'repository':kind,'coordinate':coordinate,'jarSha256':hashlib.sha256(jar.read_bytes()).hexdigest(),'resourceSha256':digest,'resourceCount':1})
    return {'typescriptBundlerExitCode':typed.returncode,'nativeNodeNextDiagnostic':node_next_diagnostic,'dom':dom,'javaResources':resolved,'bundleSha256':digest,'retainedInputCount':len(browser['inputHashes'])}
