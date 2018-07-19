# cwl-graph-generate

Generates https://view.commonwl.org/ like workflows, showing a complete workflow.

![complete workflo](https://user-images.githubusercontent.com/6304200/42953526-8f27d446-8b72-11e8-902d-b263bf881846.png)

### Example

```bash
$ git clone https://github.com/wtsi-hgi/arvados-pipelines
$ cwl-graph-generate arvados-pipelines/cwl/workflows/gatk-4.0.0.0-haplotypecaller-genotypegvcfs-libraries.cwl > graph
$ dot -Tpng graph > output.png
```

## Limitations

This project was created with the sole purpose of creating the graph above, so the code is not written from a standpoint of maintainability or stability.