// SPDX-License-Identifier: MIT
import java.nio.file.*;
import java.util.*;
import java.net.*;
import org.apache.ivy.Ivy;
import org.apache.ivy.core.settings.IvySettings;
import org.apache.ivy.plugins.resolver.IBiblioResolver;
import org.apache.ivy.plugins.parser.m2.PomModuleDescriptorParser;
import org.apache.ivy.plugins.parser.xml.XmlModuleDescriptorWriter;
import org.apache.ivy.core.module.descriptor.DefaultModuleDescriptor;
public class Convert {
  public static void main(String[] args) throws Exception {
    URL.setURLStreamHandlerFactory(protocol -> (protocol.equals("http")||protocol.equals("https"))?new URLStreamHandler(){protected URLConnection openConnection(URL url)throws java.io.IOException{throw new java.io.IOException("Native Ivy conversion has no HTTP inputs: "+url);}}:null);
    Path source=Path.of(args[0]).toRealPath(),out=Path.of(args[1]);Files.createDirectories(out);
    var settings=new IvySettings();settings.setDefaultCache(Path.of(args[2]).toFile());
    var resolver=new IBiblioResolver();resolver.setName("captured-maven");resolver.setM2compatible(true);resolver.setRoot(source.toUri().toString());resolver.setUseMavenMetadata(false);settings.addResolver(resolver);settings.setDefaultResolver(resolver.getName());
    var ivy=Ivy.newInstance(settings);ivy.pushContext();
    try(var files=Files.walk(source)) {
      for(Path pom:files.filter(p->p.getFileName().toString().endsWith(".pom")).sorted().toList()) {
        String primary=pom.getParent().getParent().getFileName()+"-"+pom.getParent().getFileName()+".pom";
        if(!pom.getFileName().toString().equals(primary))continue;
        var model=PomModuleDescriptorParser.getInstance().parseDescriptor(settings,pom.toUri().toURL(),false);
        if(!(model instanceof DefaultModuleDescriptor mutable))throw new IllegalStateException("Native Ivy returned an unsupported descriptor");
        mutable.setPublicationDate(new Date(315532800000L));mutable.setResolvedPublicationDate(new Date(315532800000L));
        var id=model.getModuleRevisionId();Path target=out.resolve(id.getOrganisation()).resolve(id.getName()).resolve(id.getRevision());if(!target.normalize().startsWith(out.normalize()))throw new IllegalStateException("Native coordinate escapes output tree");Files.createDirectories(target.resolve("ivys"));
        for(var artifact:model.getAllArtifacts()) {
          String classifier=artifact.getExtraAttribute("classifier");String filename=artifact.getName()+"-"+id.getRevision()+(classifier==null?"":"-"+classifier)+"."+artifact.getExt();Path original=pom.getParent().resolve(filename);if(!original.normalize().startsWith(source))throw new IllegalStateException("Native artifact escapes Maven tree");
          if(!Files.isRegularFile(original))throw new IllegalStateException("Native descriptor names an absent artifact: "+original);
          Path directory=target.resolve(artifact.getType()+"s");Files.createDirectories(directory);Path copied=directory.resolve(artifact.getName()+"."+artifact.getExt());Files.copy(original,copied,StandardCopyOption.REPLACE_EXISTING);
          System.out.println("artifact\t"+source.relativize(original)+"\t"+out.relativize(copied));
        }
        XmlModuleDescriptorWriter.write(model,target.resolve("ivys/ivy.xml").toFile());
        System.out.println(id+" "+Arrays.toString(model.getConfigurationsNames()));
      }
    } finally {ivy.popContext();}
  }
}
