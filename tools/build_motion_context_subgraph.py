"""Wrap a known H3 Motion Context node group in a native ComfyUI subgraph.

The generated workflow keeps the original file untouched.  It wraps the
load/apply/trim/save chain in a native ComfyUI subgraph and adds lazy switches
so the first clip still saves its latent while skipping continuation work.
"""

from __future__ import annotations

import copy
import argparse
import json
import uuid
from pathlib import Path


SOURCE_NODE_IDS = set(range(220, 230))
BOUNDARY_LINKS = {410, 411, 413, 414, 415, 416, 430, 451, 473}


def uid() -> str:
    return str(uuid.uuid4())


def main(source: Path, output: Path) -> None:
    workflow = json.loads(source.read_text(encoding="utf-8"))
    original_nodes = {node["id"]: node for node in workflow["nodes"]}
    missing = SOURCE_NODE_IDS - original_nodes.keys()
    if missing:
        raise RuntimeError(f"源工作流缺少节点: {sorted(missing)}")

    subgraph_id = uid()
    host_id = max(node["id"] for node in workflow["nodes"]) + 1

    # Keep the six real worker/path nodes. The three primitive parameter nodes
    # and the rgthree UI bypasser are replaced by promoted subgraph controls.
    inner_ids = [220, 221, 222, 223, 227, 228]
    inner_nodes = {node_id: copy.deepcopy(original_nodes[node_id]) for node_id in inner_ids}
    for node in inner_nodes.values():
        node["mode"] = 0
        node["order"] = 0
        for item in node.get("inputs", []):
            item["link"] = None
        for item in node.get("outputs", []):
            item["links"] = []

    def switch_node(node_id: int, title: str, value_type: str, pos: list[float]) -> dict:
        return {
            "id": node_id,
            "type": "ComfySwitchNode",
            "pos": pos,
            "size": [300, 108],
            "flags": {},
            "order": 0,
            "mode": 0,
            "inputs": [
                {"localized_name": "首段直通", "name": "on_false", "type": value_type, "link": None},
                {"localized_name": "续写处理", "name": "on_true", "type": value_type, "link": None},
                {
                    "localized_name": "启用续写",
                    "name": "switch",
                    "type": "BOOLEAN",
                    "widget": {"name": "switch"},
                    "link": None,
                },
            ],
            "outputs": [
                {"localized_name": "输出", "name": "output", "type": value_type, "links": []}
            ],
            "title": title,
            "properties": {
                "cnr_id": "comfy-core",
                "ver": "0.34.6",
                "Node name for S&R": "ComfySwitchNode",
            },
            "widgets_values": [False],
            "widgets_values_named": {"switch": False},
        }

    # ComfyUI treats IDs inside native subgraphs as workflow-global IDs while
    # loading. Keep new internal IDs above the original canvas maximum.
    cond_switch_id, image_switch_id, audio_switch_id = host_id + 1, host_id + 2, host_id + 3
    inner_nodes[cond_switch_id] = switch_node(
        cond_switch_id, "首段直通 / 续写 Conditioning", "CONDITIONING", [930, 120]
    )
    inner_nodes[image_switch_id] = switch_node(
        image_switch_id, "首段直通 / 续写画面裁剪", "IMAGE", [930, 430]
    )
    inner_nodes[audio_switch_id] = switch_node(
        audio_switch_id, "首段直通 / 续写音频裁剪", "AUDIO", [930, 590]
    )

    # Make the expanded subgraph readable.
    positions = {
        227: [20, 760],
        228: [360, 820],
        221: [20, 250],
        220: [410, 150],
        222: [600, 470],
        223: [720, 800],
    }
    for node_id, pos in positions.items():
        inner_nodes[node_id]["pos"] = pos

    inputs: list[dict] = []
    outputs: list[dict] = []
    links: list[dict] = []
    next_link = 1

    def add_input(name: str, value_type: str, label: str | None = None) -> int:
        index = len(inputs)
        entry = {
            "id": uid(),
            "name": name,
            "type": value_type,
            "linkIds": [],
            "pos": [-236, 80 + index * 24],
        }
        if label:
            entry["label"] = label
        inputs.append(entry)
        return index

    def add_output(name: str, value_type: str, label: str | None = None) -> int:
        index = len(outputs)
        entry = {
            "id": uid(),
            "name": name,
            "type": value_type,
            "linkIds": [],
            "pos": [1280, 120 + index * 28],
        }
        if label:
            entry["label"] = label
        outputs.append(entry)
        return index

    def connect(origin_id: int, origin_slot: int, target_id: int, target_slot: int, value_type: str) -> int:
        nonlocal next_link
        link_id = next_link
        next_link += 1
        links.append(
            {
                "id": link_id,
                "origin_id": origin_id,
                "origin_slot": origin_slot,
                "target_id": target_id,
                "target_slot": target_slot,
                "type": value_type,
            }
        )
        if origin_id == -10:
            inputs[origin_slot]["linkIds"].append(link_id)
        else:
            inner_nodes[origin_id]["outputs"][origin_slot]["links"].append(link_id)
        if target_id == -20:
            outputs[target_slot]["linkIds"].append(link_id)
        else:
            inner_nodes[target_id]["inputs"][target_slot]["link"] = link_id
        return link_id

    # Public controls first, followed by the six workflow connections.
    i_enabled = add_input("enabled", "BOOLEAN", "续写模式（首段关闭）")
    i_project = add_input("project_name", "STRING", "项目名称")
    i_previous = add_input("previous_clip", "INT", "上一段编号")
    i_current = add_input("current_clip", "INT", "本段编号")
    i_context_length = add_input("context_length", "COMBO", "画面继承帧数")
    i_audio_context = add_input("audio_context_length", "INT", "音频继承帧数")
    i_fps = add_input("fps", "FLOAT", "帧率")
    i_match_tail = add_input("match_tail", "BOOLEAN", "从尾部匹配")
    i_conditioning = add_input("conditioning", "CONDITIONING", "conditioning")
    i_vae = add_input("vae", "VAE", "video VAE")
    i_latent = add_input("latent", "LATENT", "当前段初始 latent")
    i_images = add_input("images", "IMAGE", "解码画面")
    i_audio = add_input("audio", "AUDIO", "解码音频")
    i_final_latent = add_input("final_latent", "LATENT", "本段最终 latent")

    o_conditioning = add_output("conditioning", "CONDITIONING", "处理后 conditioning")
    o_images = add_output("images", "IMAGE", "处理后画面")
    o_audio = add_output("audio", "AUDIO", "处理后音频")
    o_path = add_output("latent_path", "STRING", "保存路径")

    # Promoted widgets and path construction.
    connect(-10, i_project, 227, 1, "STRING")
    connect(-10, i_previous, 221, 1, "INT")
    connect(-10, i_current, 223, 2, "INT")
    connect(-10, i_context_length, 220, 7, "COMBO")
    connect(-10, i_audio_context, 220, 8, "INT")
    connect(-10, i_fps, 222, 3, "FLOAT")
    connect(-10, i_match_tail, 222, 4, "BOOLEAN")
    connect(227, 0, 221, 0, "STRING")
    connect(227, 0, 228, 0, "STRING")
    connect(228, 0, 223, 1, "STRING")

    # Continuation branch. Core If/Else nodes use lazy inputs, so the load and
    # Motion Context branch does not run for the first clip.
    connect(-10, i_conditioning, 220, 0, "CONDITIONING")
    connect(-10, i_conditioning, cond_switch_id, 0, "CONDITIONING")
    connect(-10, i_vae, 220, 1, "VAE")
    connect(-10, i_latent, 220, 2, "LATENT")
    connect(221, 0, 220, 4, "LATENT")
    connect(220, 0, cond_switch_id, 1, "CONDITIONING")
    connect(-10, i_enabled, cond_switch_id, 2, "BOOLEAN")
    connect(cond_switch_id, 0, -20, o_conditioning, "CONDITIONING")

    connect(-10, i_images, 222, 0, "IMAGE")
    connect(-10, i_audio, 222, 1, "AUDIO")
    connect(220, 1, 222, 2, "INT")
    connect(-10, i_images, image_switch_id, 0, "IMAGE")
    connect(222, 0, image_switch_id, 1, "IMAGE")
    connect(-10, i_enabled, image_switch_id, 2, "BOOLEAN")
    connect(image_switch_id, 0, -20, o_images, "IMAGE")
    connect(-10, i_audio, audio_switch_id, 0, "AUDIO")
    connect(222, 1, audio_switch_id, 1, "AUDIO")
    connect(-10, i_enabled, audio_switch_id, 2, "BOOLEAN")
    connect(audio_switch_id, 0, -20, o_audio, "AUDIO")

    # Saving is deliberately outside the conditional branch. This preserves
    # the original first-clip behavior and creates the context for clip two.
    connect(-10, i_final_latent, 223, 0, "LATENT")
    connect(223, 0, -20, o_path, "STRING")

    for order, node_id in enumerate(
        [227, 228, 221, 220, 222, 223, cond_switch_id, image_switch_id, audio_switch_id]
    ):
        inner_nodes[node_id]["order"] = order

    subgraph_group_id = max((g.get("id", 0) for g in workflow.get("groups", [])), default=0) + 1

    subgraph = {
        "id": subgraph_id,
        "version": 1,
        "state": {
            "lastGroupId": subgraph_group_id,
            "lastNodeId": max(inner_nodes),
            "lastLinkId": next_link - 1,
            "lastRerouteId": 0,
        },
        "revision": 1,
        "config": {},
        "name": "Motion Context 一键续写",
        "inputNode": {"id": -10, "bounding": [-260, 40, 220, 520]},
        "outputNode": {"id": -20, "bounding": [1260, 80, 180, 160]},
        "inputs": inputs,
        "outputs": outputs,
        "widgets": [],
        "nodes": list(inner_nodes.values()),
        "groups": [
            {
                "id": subgraph_group_id,
                "title": "内部逻辑｜首段直通，续写段加载与裁剪",
                "bounding": [-20, 70, 1220, 650],
                "color": "#3f789e",
                "flags": {},
            }
        ],
        "links": links,
        "extra": {},
    }

    # Replace all ten old canvas nodes with one native subgraph host.
    workflow["nodes"] = [n for n in workflow["nodes"] if n["id"] not in SOURCE_NODE_IDS]
    project_value = original_nodes[224].get("widgets_values_named", {}).get(
        "value", original_nodes[224].get("widgets_values", [""])[0]
    )
    previous_value = original_nodes[225].get("widgets_values_named", {}).get("value", 1)
    current_value = original_nodes[226].get("widgets_values_named", {}).get("value", 2)
    continuation_default = original_nodes[220].get("mode", 0) == 0
    widget_values = [
        continuation_default,
        project_value,
        previous_value,
        current_value,
        "22",
        24,
        24.0,
        True,
    ]
    widget_names = [
        "enabled",
        "project_name",
        "previous_clip",
        "current_clip",
        "context_length",
        "audio_context_length",
        "fps",
        "match_tail",
    ]

    # Existing boundary link IDs are retained so all neighboring node records
    # remain valid. Only their endpoint changes to the host node.
    top_links = []
    for link in workflow["links"]:
        link_id, origin_id, origin_slot, target_id, target_slot, value_type = link
        if link_id not in BOUNDARY_LINKS and (origin_id in SOURCE_NODE_IDS or target_id in SOURCE_NODE_IDS):
            continue
        if link_id == 410:
            target_id, target_slot = host_id, i_conditioning
        elif link_id == 411:
            target_id, target_slot = host_id, i_latent
        elif link_id == 451:
            target_id, target_slot = host_id, i_vae
        elif link_id == 415:
            target_id, target_slot = host_id, i_images
        elif link_id == 416:
            target_id, target_slot = host_id, i_audio
        elif link_id == 414:
            target_id, target_slot = host_id, i_final_latent
        elif link_id == 413:
            origin_id, origin_slot = host_id, o_conditioning
        elif link_id == 430:
            origin_id, origin_slot = host_id, o_images
        elif link_id == 473:
            origin_id, origin_slot = host_id, o_audio
        top_links.append([link_id, origin_id, origin_slot, target_id, target_slot, value_type])
    workflow["links"] = top_links

    host_input_links = {
        i_conditioning: 410,
        i_vae: 451,
        i_latent: 411,
        i_images: 415,
        i_audio: 416,
        i_final_latent: 414,
    }
    host_inputs = []
    for index, item in enumerate(inputs):
        entry = {
            "name": item["name"],
            "type": item["type"],
            "link": host_input_links.get(index),
        }
        if "label" in item:
            entry["label"] = item["label"]
        if index < len(widget_values):
            entry["widget"] = {"name": item["name"]}
        host_inputs.append(entry)

    host_outputs = [
        {"label": outputs[0]["label"], "name": "conditioning", "type": "CONDITIONING", "links": [413]},
        {"label": outputs[1]["label"], "name": "images", "type": "IMAGE", "links": [430]},
        {"label": outputs[2]["label"], "name": "audio", "type": "AUDIO", "links": [473]},
        {"label": outputs[3]["label"], "name": "latent_path", "type": "STRING", "links": []},
    ]
    host = {
        "id": host_id,
        "type": subgraph_id,
        "pos": [-60, 4405],
        "size": [520, 410],
        "flags": {"collapsed": False},
        "order": min(original_nodes[n]["order"] for n in SOURCE_NODE_IDS),
        "mode": 0,
        "inputs": host_inputs,
        "outputs": host_outputs,
        "title": "Motion Context 一键续写｜首段关，第二段起开",
        "properties": {
            "cnr_id": "comfy-core",
            "ver": "0.34.6",
            "Node name for S&R": "Motion Context 一键续写",
            "ue_properties": {
                "widget_ue_connectable": {name: True for name in widget_names},
                "version": "7.8",
                "input_ue_unconnectable": {},
            },
        },
        "widgets_values": widget_values,
        "widgets_values_named": dict(zip(widget_names, widget_values)),
        "color": "#1f1f48",
        "bgcolor": "rgba(24,24,27,.9)",
    }
    workflow["nodes"].append(host)

    # Remove the old rgthree-controlled group. The new boolean is deterministic
    # at execution time and works inside the saved workflow/API graph.
    workflow["groups"] = [g for g in workflow.get("groups", []) if g.get("id") != 7]
    workflow.setdefault("definitions", {})["subgraphs"] = [subgraph]
    workflow["last_node_id"] = max(
        workflow.get("last_node_id", 0), host_id, cond_switch_id, image_switch_id, audio_switch_id
    )

    validate(workflow, host_id, subgraph)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(workflow, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"created: {output}")
    print(f"host node: {host_id}; subgraph: {subgraph_id}")
    print(f"top nodes: {len(workflow['nodes'])}; top links: {len(workflow['links'])}")


def validate(workflow: dict, host_id: int, subgraph: dict) -> None:
    node_ids = [node["id"] for node in workflow["nodes"]]
    if len(node_ids) != len(set(node_ids)):
        raise RuntimeError("顶层节点 ID 重复")
    node_by_id = {node["id"]: node for node in workflow["nodes"]}
    for link in workflow["links"]:
        link_id, origin_id, origin_slot, target_id, target_slot, _ = link
        if origin_id not in node_by_id or target_id not in node_by_id:
            raise RuntimeError(f"顶层悬空连线 {link_id}: {origin_id} -> {target_id}")
        if origin_slot >= len(node_by_id[origin_id].get("outputs", [])):
            raise RuntimeError(f"顶层连线 {link_id} 输出槽越界")
        if target_slot >= len(node_by_id[target_id].get("inputs", [])):
            raise RuntimeError(f"顶层连线 {link_id} 输入槽越界")
    if any(node_id in SOURCE_NODE_IDS for node_id in node_ids):
        raise RuntimeError("旧 Motion Context 节点仍留在顶层")
    if host_id not in node_by_id:
        raise RuntimeError("缺少子图宿主节点")

    inner_ids = {node["id"] for node in subgraph["nodes"]}
    link_ids = set()
    for link in subgraph["links"]:
        link_id = link["id"]
        if link_id in link_ids:
            raise RuntimeError(f"子图连线 ID 重复: {link_id}")
        link_ids.add(link_id)
        if link["origin_id"] not in inner_ids | {-10}:
            raise RuntimeError(f"子图连线 {link_id} 起点不存在")
        if link["target_id"] not in inner_ids | {-20}:
            raise RuntimeError(f"子图连线 {link_id} 终点不存在")
    for item in subgraph["inputs"] + subgraph["outputs"]:
        if any(link_id not in link_ids for link_id in item["linkIds"]):
            raise RuntimeError(f"子图端口 {item['name']} 引用了不存在的连线")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Wrap the supported H3 Motion Context node group in a native ComfyUI subgraph."
    )
    parser.add_argument("source", type=Path, help="source ComfyUI workflow JSON")
    parser.add_argument("output", type=Path, help="destination JSON; source is never overwritten")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("source and output must be different files")
    main(args.source, args.output)
