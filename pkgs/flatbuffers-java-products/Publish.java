// SPDX-License-Identifier: MIT
import java.io.FileWriter;
import org.apache.maven.model.Model;
import org.apache.maven.model.Dependency;
import org.apache.maven.model.io.xpp3.MavenXpp3Writer;
public final class Publish {
  public static void main(String[] args) throws Exception {
    Model model = new Model();
    model.setModelVersion("4.0.0");
    model.setGroupId(args[0]); model.setArtifactId(args[1]); model.setVersion(args[2]);
    model.setPackaging("jar");
    Dependency dependency = new Dependency();
    dependency.setGroupId(args[3]); dependency.setArtifactId(args[4]); dependency.setVersion(args[5]);
    model.addDependency(dependency);
    try (FileWriter writer = new FileWriter(args[6])) { new MavenXpp3Writer().write(writer, model); }
  }
}
