import argparse
import json
import re
import sys
import textwrap
from collections import Counter
from pprint import pprint
from typing import IO, Any, Dict, Text
from os import path
import logging

from cwltool.command_line_tool import CommandLineTool, ExpressionTool
from cwltool.load_tool import (fetch_document, resolve_tool_uri,
                               resolve_and_validate_document, make_tool)
from cwltool.workflow import Workflow
from cwltool.context import LoadingContext, RuntimeContext, getdefault
import urllib

_logger = logging.getLogger(__name__)

def get_end_url(url):
    return str(url).split("/")[-1]

def get_url_hash(url):
    return str(url).split("#")[-1]

def get_before_hash(uri):
    if uri.rfind("#") == -1:
        return uri

    return str(uri)[:uri.rfind("#")]

def get_end_name(name):
    hash_regions = str(name).split("#")
    if len(hash_regions) == 2:
        return hash_regions[1]
    else:
        return str(name).split("/")[-1]

def get_out_name(url):
    last_hash = url.rfind("#")
    last_slash = url.rfind("/")
    if last_hash == -1 and last_slash == -1:
        return url

    return url[(last_hash if last_hash > last_slash else last_slash) + 1:]

def print_indent(string):
    print(" " * indent_level + string)

def get_tool_name(url):
    if url.rfind("/") < url.rfind("#"):
        return url

    return "/".join(url.split("/")[:-1])

tool_names = set()

drawn_workflows = set()
uuid_num = 0

def get_uid():
    global uuid_num
    uuid_num += 1
    return f"{uuid_num}"

def esc(string):
    if isinstance(string, bool):
        return "true" if string else "false"
    elif isinstance(string, str) \
            and len(string) >= 3 \
            and (string[:2], string[-1]) in (("${", "}"), ("$(", ")")):
        string = string[2:-1]
    else:
        string = repr(string)

    return string \
        .replace("\"", "\\\"") \
        .replace("{", "\\{") \
        .replace("}", "\\}")

arrows = []
transforms = []

def tu(uri):
    global transforms
    for transform in transforms:
        uri = uri.replace(*transform)

    return uri

ids_by_workflow = dict()

def get_props_str(props_dict):
    if props_dict == {}:
        return ""

    props_arr = []
    for key, value in props_dict.items():
        props_arr.append(f"{key}=\"{value}\"")

    return "[" + ", ".join(props_arr) + "]"

def shortname(inputid):
    # type: (Text) -> Text
    d = urllib.parse.urlparse(inputid)
    if d.fragment:
        return d.fragment.split(u"/")[-1]
    else:
        return d.path.split(u"/")[-1]

def endId(tool_id, embedded_tool_part):
    tool_shortname = shortname(tool_id)
    for x in embedded_tool_part:
        if tool_shortname == shortname(x["id"]):
            return x["id"]

    raise NotImplementedError()

def get_workflow_dot(tool, repeat_times, workflow_id):
    global drawn_workflows
    global tool_names
    global indent_level
    global arrows
    global transforms
    global ids_by_workflow
    drawing_workflow_id = workflow_id
    ids_by_workflow[tool.tool["id"]] = workflow_id
    def draw_node(node_id, label, **props):
        props["label"] = label

        if props.get("peripheries") is None:
            props["peripheries"] = repeat_times

        print_indent(f""""{tu(node_id)}{"" if node_id [0:4] != "file" else ("#" + workflow_id)}" {get_props_str(props)};""")


    def draw_arrow(source, target, label=None, is_double_arrow=False, source_step=None, **props):
        if label is not None:
            props["label"] = f"  {label}  "

        if is_double_arrow:
            props["arrowhead"] = "normalnormal"

        _logger.debug(f"Output step name “{source_step}”")
        source_num = ids_by_workflow.get(source_step, ids_by_workflow.get(get_before_hash(source)))
        target_num = ids_by_workflow.get(get_before_hash(target))
        try:
            if source[0:4] == "file":
                assert source_num is not None
            if target[0:4] == "file":
                assert target_num is not None
        except:
            import pdb; pdb.set_trace()

        arrows.append(f""""{source}{"" if source_num is None else "#" + str(source_num)}" -> "{target}{"" if target_num is None else "#" + str(target_num)}" {get_props_str(props)};""")

    print_indent(f"""subgraph "cluster_{get_end_name(tool.tool["id"])}{get_uid()}" {{""")
    indent_level += 2
    print_indent(f"""color=grey""")
    print_indent(f"""label="{get_end_name(tool.tool["id"])}\";""")

    print_indent(f"subgraph cluster_inputs{get_uid()} {{")
    indent_level += 2
    print_indent("rank = \"same\";")
    print_indent("style = \"dashed\";")
    print_indent("label = \"Workflow Inputs\";")
    input_steps = set()
    for cwl_input in tool.tool["inputs"]:
        input_steps.add(cwl_input["id"])
        draw_node(cwl_input["id"], get_end_name(cwl_input["id"]), fillcolor="#94DDF4")
        # TODO add a label
    indent_level -= 2
    print_indent("}")

    inputs_id_to_end_id = dict()
    outputs_id_to_end_id = dict()
    workflows_to_draw = []
    for cwl_step in tool.steps:
        if not isinstance(cwl_step.embedded_tool, Workflow):
            tool_names.add(cwl_step.id)

        for y in cwl_step.tool["inputs"]:
            inputs_id_to_end_id[y["id"]] = endId(y["id"], cwl_step.embedded_tool.tool["inputs"]) #y["endId"]

        for y in cwl_step.tool["outputs"]:
            outputs_id_to_end_id[y["id"]] = endId(y["id"], cwl_step.embedded_tool.tool["outputs"])

    steps_by_id = dict()
    for cwl_step in tool.steps:
        steps_by_id[cwl_step.id] = cwl_step

    for dict_cwl_step in tool.tool["steps"]:
        cwl_step = steps_by_id[dict_cwl_step["id"]]
        drawing_workflow_id = workflow_id
        step_target_suffix = ""
        if isinstance(cwl_step.embedded_tool, Workflow):
            drawing_workflow_id = get_uid()

            ids_by_workflow[cwl_step.id] = drawing_workflow_id
            _logger.debug(f"Adding “{cwl_step.id}”")
            drawn_workflows.add(cwl_step.embedded_tool.tool["id"])
            #workflows_to_draw.append(cwl_step.embedded_tool)
            inner_wf_repeat_times = repeat_times
            if cwl_step.tool.get("scatter") is not None:
                inner_wf_repeat_times += 1
            get_workflow_dot(cwl_step.embedded_tool, inner_wf_repeat_times, drawing_workflow_id)
        else:
            props = {}

            if isinstance(cwl_step.embedded_tool, ExpressionTool):
                props["fillcolor"] = "#d3d3d3"
            else:
                assert isinstance(cwl_step.embedded_tool, CommandLineTool)

            item_repeat_times = repeat_times

            if cwl_step.tool.get("scatter") is not None:
                item_repeat_times += 1

            props["peripheries"] = item_repeat_times

            draw_node(cwl_step.id, get_end_name(cwl_step.id), **props)

        for cwl_step_input in cwl_step.tool["inputs"]:
            arrow_target = endId(cwl_step_input["id"], cwl_step.embedded_tool.tool["inputs"]) #cwl_step_input["endId"]
            if get_tool_name(cwl_step_input["id"]) in tool_names:
                arrow_target = cwl_step.id
            else:
                pass

            if cwl_step_input.get("source") is None and cwl_step_input.get("valueFrom") is not None:
                # old_regex = r"\$\(inputs\.(\w+).*?\)"
                js_expression_references = re.findall(r"inputs\.(\w+).*?", cwl_step_input["valueFrom"])
                if len(js_expression_references) != 0:
                    def find_input_source(input_id_name):
                        for x in cwl_step.tool["inputs"]:
                            if shortname(x["id"]) == input_id_name:
                                return x["source"]

                    cwl_step_input["source"] = list(map(lambda x: find_input_source(x), js_expression_references))

            if cwl_step_input.get("source") is None:
                assert cwl_step_input.get("valueFrom") is not None or cwl_step_input.get("default") is not None
                value = cwl_step_input.get("default", cwl_step_input.get("valueFrom"))
                default_node_name = f"fixed_name{get_uid()}"
                draw_node(default_node_name, esc(value), fillcolor="#d5aefc")

                draw_arrow(default_node_name, arrow_target, get_out_name(cwl_step_input["id"]))
            else:
                assert cwl_step_input.get("source") is not None
                if isinstance(cwl_step_input["source"], str):
                    source_list = [cwl_step_input["source"]]
                else:
                    source_list = cwl_step_input["source"]

                if cwl_step_input.get("valueFrom") is not None:
                    value_from_node_name = f"value_from_node{get_uid()}"
                    draw_node(value_from_node_name, esc(cwl_step_input["valueFrom"]), fillcolor="#ffa07a")

                for source_item in source_list:
                    assert isinstance(source_item, str)

                    is_double_arrow = False
                    if cwl_step.tool.get("scatter") is not None and cwl_step_input["id"] in cwl_step.tool["scatter"]:
                        is_double_arrow = True

                    if get_tool_name(source_item) in tool_names:
                        arrow_source = get_tool_name(source_item)
                    else:
                        arrow_source = outputs_id_to_end_id.get(source_item, source_item)

                    if cwl_step_input.get("valueFrom") is None:
                        if arrow_source in input_steps:
                            # i.e. this is an input step
                            draw_arrow(arrow_source, arrow_target, source_step=get_tool_name(source_item), is_double_arrow=is_double_arrow)
                        else:
                            draw_arrow(arrow_source, arrow_target, get_out_name(source_item), is_double_arrow, source_step=get_tool_name(source_item))
                    else:
                        draw_arrow(arrow_source, value_from_node_name, source_step=get_tool_name(source_item))
                        draw_arrow(value_from_node_name, arrow_target, get_out_name(source_item))

    print_indent(f"subgraph cluster_outputs{get_uid()} {{")
    indent_level += 2
    print_indent("rank = \"same\";")
    print_indent("style = \"dashed\";")
    print_indent("labelloc = \"b\";")
    print_indent("label = \"Workflow Outputs\";")
    for cwl_output in tool.tool["outputs"]:
        draw_node(cwl_output["id"], get_end_name(cwl_output["id"]), fillcolor="#94DDF4")

        if isinstance(cwl_output["outputSource"], str):
            cwl_output_source_list = [cwl_output["outputSource"]]
        else:
            cwl_output_source_list = cwl_output["outputSource"]

        for cwl_output_source in cwl_output_source_list:
            assert isinstance(cwl_output_source, str)

            if get_tool_name(cwl_output_source) in tool_names:
                arrow_source = get_tool_name(cwl_output_source)
            else:
                arrow_source = outputs_id_to_end_id[cwl_output_source]

            draw_arrow(arrow_source, cwl_output["id"], get_out_name(cwl_output_source), source_step=get_tool_name(cwl_output_source))

    indent_level -= 2
    print_indent("}")

    indent_level -= 2
    print_indent("}")


start = """
    digraph workflow {
      graph [
        bgcolor = "#eeeeee"
        color = "black"
        fontsize = "10"
        clusterrank = "local"
        newrank = true # NOTE: is this attribute is not set, the graph doesn't display very well at all
        # labeljust = "left"
        # ranksep = "0.22"
        # nodesep = "0.05"
      ]

      node [
        fontname = "Helvetica"
        fontsize = "10"
        fontcolor = "black"
        shape = "rect"
        height = "0"
        width = "0"
        color = "black"
        fillcolor = "lightgoldenrodyellow"
        style = "filled"
      ];

      edge [
        fontname="Helvetica"
        fontsize="8"
        fontcolor="black"
        color="black"
        # arrowsize="0.7"
      ];"""

def cwl_viewer_dot(tool_json):
    global indent_level
    global arrows
    print(textwrap.dedent(start))
    indent_level = 2
    get_workflow_dot(tool_json, 1, get_uid())
    for arrow in arrows:
        print_indent(arrow)
    print("}")


def cwl_graph_generate(cwl_path: str):
    if cwl_path[:5] != "file:":
        cwl_path = f"file://{path.abspath(cwl_path)}"

    document_loader, workflowobj, uri = fetch_document(cwl_path)
    document_loader, uri = resolve_and_validate_document(document_loader, workflowobj, uri, preprocess_only=True)
    loadingContext = LoadingContext()
    tool = make_tool(uri, document_loader)
    cwl_viewer_dot(tool)

def main():
    parser = argparse.ArgumentParser(__name__)
    parser.add_argument("file_location", help="File location of the CWL workflow to generate")
    args = parser.parse_args()

    cwl_graph_generate(args.file_location)

if __name__ == '__main__':
    main()

