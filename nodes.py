"""Small UX helpers for the Motion Context one-node workflow.

The nodes deliberately do not replace H3 Motion Context. They only recover a
saved clip slot from video metadata and guard a numbered slot before sampling.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import folder_paths
from PIL import Image


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
EMPTY_VIDEO = "（请选择上一段视频）"


def _output_root() -> Path:
    return Path(folder_paths.get_output_directory()).resolve()


def _input_root() -> Path:
    return Path(folder_paths.get_input_directory()).resolve()


def _inside_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _inside_output(path: Path) -> bool:
    return _inside_root(path, _output_root())


def _video_root(source: str) -> Path:
    if source == "output":
        return _output_root()
    if source == "input":
        return _input_root()
    raise ValueError("不支持的视频来源。")


def _video_choices() -> list[str]:
    root = _output_root()
    rows: list[tuple[float, str]] = []
    try:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                try:
                    stamp = path.stat().st_mtime
                except OSError:
                    stamp = 0.0
                rows.append((stamp, path.relative_to(root).as_posix()))
    except OSError:
        pass
    rows.sort(key=lambda item: (-item[0], item[1].lower()))
    return [EMPTY_VIDEO] + [item[1] for item in rows]


def _json_object(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _workflow_from_png(path: Path):
    try:
        with Image.open(path) as image:
            return _json_object(image.info.get("workflow"))
    except (OSError, ValueError):
        return None


def _sidecar_candidates(video: Path) -> list[Path]:
    stem = video.stem
    exact_stems = [stem]
    if stem.endswith("-audio"):
        exact_stems.append(stem[:-6])
    candidates = [video.with_name(name + ".png") for name in exact_stems]
    existing = [path for path in candidates if path.is_file()]
    if existing:
        return existing

    # Renaming only the MP4 breaks the shared stem. VHS writes its PNG within
    # a moment of the video, so use the closest metadata PNG as a fallback.
    try:
        video_time = video.stat().st_mtime
        nearby = []
        for path in video.parent.glob("*.png"):
            try:
                delta = abs(path.stat().st_mtime - video_time)
            except OSError:
                continue
            if delta <= 8.0:
                nearby.append((delta, path))
        nearby.sort(key=lambda item: item[0])
        return [item[1] for item in nearby]
    except OSError:
        return []


def _unescape_ffmetadata(value: str) -> str:
    result = []
    escaped = False
    for char in value:
        if escaped:
            result.append("\n" if char == "n" else char)
            escaped = False
        elif char == "\\":
            escaped = True
        else:
            result.append(char)
    if escaped:
        result.append("\\")
    return "".join(result)


def _workflow_from_video(video: Path):
    """Read the workflow tag VHS stores inside videos when metadata is on."""
    try:
        from videohelpersuite.utils import ffmpeg_path
    except Exception:
        ffmpeg_path = None
    if not ffmpeg_path:
        try:
            from imageio_ffmpeg import get_ffmpeg_exe

            ffmpeg_path = get_ffmpeg_exe()
        except Exception:
            ffmpeg_path = None
    if not ffmpeg_path:
        return None
    try:
        proc = subprocess.run(
            [ffmpeg_path, "-v", "error", "-i", str(video), "-f", "ffmetadata", "-"],
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = proc.stdout.decode("utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("workflow="):
            return _json_object(_unescape_ffmetadata(line[len("workflow=") :]))
    return None


def _workflow_for_video(video: Path):
    workflow = _workflow_from_video(video)
    if workflow:
        return workflow, "视频内嵌元数据"
    for sidecar in _sidecar_candidates(video):
        workflow = _workflow_from_png(sidecar)
        if workflow:
            return workflow, f"伴随图片 {sidecar.name}"
    return None, ""


def _slot_from_workflow(workflow: dict):
    nodes = workflow.get("nodes") or []
    node_by_id = {node.get("id"): node for node in nodes}
    link_by_id = {}
    for link in workflow.get("links") or []:
        if isinstance(link, list) and len(link) >= 6:
            link_by_id[link[0]] = link

    def primitive_value(node):
        named = node.get("widgets_values_named") or {}
        values = node.get("widgets_values") or []
        return named.get("value", values[0] if values else None)

    def input_value(node, slot):
        inputs = node.get("inputs") or []
        if slot >= len(inputs):
            return None
        item = inputs[slot]
        link = link_by_id.get(item.get("link"))
        if link:
            source = node_by_id.get(link[1])
            if not source:
                return None
            if source.get("type") in {"PrimitiveString", "PrimitiveInt", "PrimitiveFloat"}:
                return primitive_value(source)
            if source.get("type") == "StringConcatenate":
                left = input_value(source, 0)
                right = input_value(source, 1)
                named = source.get("widgets_values_named") or {}
                values = source.get("widgets_values") or []
                if left is None:
                    left = named.get("string_a", values[0] if values else "")
                if right is None:
                    right = named.get("string_b", values[1] if len(values) > 1 else "")
                delimiter = named.get("delimiter", values[2] if len(values) > 2 else "")
                return f"{left}{delimiter}{right}"
        named = node.get("widgets_values_named") or {}
        values = node.get("widgets_values") or []
        name = item.get("name")
        if name in named:
            return named[name]
        widget_slots = [entry for entry in inputs[: slot + 1] if entry.get("widget")]
        index = len(widget_slots) - 1
        return values[index] if 0 <= index < len(values) else None

    # v1/v2 native subgraph host. The UUID node type changes between builds,
    # so identify it by its stable title and named widget values.
    for node in nodes:
        title = str(node.get("title") or "")
        named = node.get("widgets_values_named") or {}
        if title.startswith("Motion Context 一键续写") and "current_clip" in named:
            clip_index = int(named["current_clip"])
            project = str(named.get("project_name") or "").strip("/\\")
            prefix = f"h3_context/{project}/clip" if project else "h3_context/clip"
            return prefix, clip_index

    # The original blockout workflow drives Save Latent through separate
    # project/current-number primitives. Its Save node widget values are stale
    # once those sockets are linked, so read the actual driver nodes first.
    project_node = next(
        (node for node in nodes if str(node.get("title") or "").endswith("项目名称")), None
    )
    current_node = next(
        (node for node in nodes if node.get("title") == "本段编号"), None
    )
    if project_node and current_node:
        project_named = project_node.get("widgets_values_named") or {}
        current_named = current_node.get("widgets_values_named") or {}
        project_values = project_node.get("widgets_values") or []
        current_values = current_node.get("widgets_values") or []
        project = str(
            project_named.get("value", project_values[0] if project_values else "")
        ).strip("/\\")
        clip_index = int(
            current_named.get("value", current_values[0] if current_values else 0)
        )
        prefix = f"h3_context/{project}/clip" if project else "h3_context/clip"
        return prefix, clip_index

    # Original unwrapped Motion Context workflow. Resolve linked inputs first;
    # their saved widget values can be stale after a socket is connected.
    for node in nodes:
        if node.get("type") != "MiniMaxH3MotionContextSaveLatent":
            continue
        linked_prefix = input_value(node, 1)
        linked_clip = input_value(node, 2)
        if linked_prefix is not None and linked_clip is not None:
            return str(linked_prefix), int(linked_clip)
        named = node.get("widgets_values_named") or {}
        values = node.get("widgets_values") or []
        prefix = named.get("filename_prefix", values[0] if values else "h3_context/clip")
        clip_index = named.get("clip_index", values[1] if len(values) > 1 else 0)
        return str(prefix), int(clip_index)
    raise ValueError("视频工作流中没有找到 Motion Context latent 保存信息。")


def _slot_path(filename_prefix: str, clip_index: int) -> Path:
    if clip_index <= 0:
        raise ValueError("视频使用的是自动编号 latent，无法可靠映射到固定 Clip 编号。")
    prefix = Path(str(filename_prefix).strip().strip('"').strip("'"))
    resolved_prefix = prefix.resolve() if prefix.is_absolute() else (_output_root() / prefix).resolve()
    path = resolved_prefix.parent / f"{resolved_prefix.name}_{clip_index:05d}.safetensors"
    if not _inside_output(path):
        raise ValueError("解析出的 latent 路径不在 ComfyUI output 目录内。")
    return path.resolve()


class DeepWhiteH3VideoLatentLookup:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "previous_video": (
                    _video_choices(),
                    {"tooltip": "选择要继续的视频，自动读取其 Clip 编号和 latent 路径。"},
                )
            }
        }

    RETURN_TYPES = ("STRING", "INT", "STRING")
    RETURN_NAMES = ("latent_path", "clip_index", "status")
    FUNCTION = "lookup"
    CATEGORY = "conditioning/minimax"
    DESCRIPTION = "按已生成视频反查 Motion Context latent。"

    @classmethod
    def IS_CHANGED(cls, previous_video):
        if previous_video == EMPTY_VIDEO:
            return previous_video
        path = (_output_root() / previous_video).resolve()
        try:
            return f"{previous_video}:{path.stat().st_mtime_ns}:{path.stat().st_size}"
        except OSError:
            return f"{previous_video}:missing"

    def lookup(self, previous_video):
        return _lookup_video(previous_video)


def _lookup_video(previous_video, source="output"):
    if not previous_video or previous_video == EMPTY_VIDEO:
        raise ValueError("请先选择或上传一个视频。")
    root = _video_root(source)
    video = (root / previous_video).resolve()
    if not _inside_root(video, root) or not video.is_file():
        raise FileNotFoundError(f"找不到视频：{previous_video}")
    if video.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("上传的文件不是支持的视频格式。")
    if source == "input":
        workflow = _workflow_from_video(video)
        metadata_source = "上传视频内嵌元数据"
    else:
        workflow, metadata_source = _workflow_for_video(video)
    if not workflow:
        if source == "input":
            raise ValueError(
                "上传的视频没有可读取的 ComfyUI 工作流元数据。"
                "如果视频经过剪辑、转码或平台下载，内嵌元数据可能已经丢失。"
            )
        raise ValueError(
            "视频没有可读取的 ComfyUI 工作流元数据，也没有找到对应的 VHS PNG。"
        )
    prefix, clip_index = _slot_from_workflow(workflow)
    path = _slot_path(prefix, clip_index)
    if not path.is_file():
        raise FileNotFoundError(
            f"视频对应 Clip {clip_index}，但 latent 文件不存在：{path}"
        )
    relative = path.relative_to(_output_root()).as_posix()
    status = f"已通过{metadata_source}找到 Clip {clip_index}：{relative}"
    return (relative, clip_index, status)


class DeepWhiteH3LatentSlotCheck:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "conditioning": ("CONDITIONING",),
                "filename_prefix": ("STRING", {"default": "h3_context/clip"}),
                "clip_index": ("INT", {"default": 1, "min": 1, "max": 9999, "step": 1}),
                "overwrite_existing": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "label_on": "允许覆盖",
                        "label_off": "拒绝覆盖",
                    },
                ),
            }
        }

    RETURN_TYPES = ("CONDITIONING", "STRING")
    RETURN_NAMES = ("conditioning", "status")
    FUNCTION = "check"
    CATEGORY = "conditioning/minimax"
    DESCRIPTION = "在采样前检查目标 Clip latent 是否已存在。"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def check(self, conditioning, filename_prefix, clip_index, overwrite_existing=False):
        path = _slot_path(filename_prefix, int(clip_index))
        if path.exists() and not overwrite_existing:
            relative = path.relative_to(_output_root()).as_posix()
            raise RuntimeError(
                f"Latent 编号已占用：Clip {clip_index} → {relative}。"
                "如确认要替换该版本，请打开“允许覆盖已有 latent”后重新运行。"
            )
        status = (
            f"Clip {clip_index} 已存在，本次允许覆盖。"
            if path.exists()
            else f"Clip {clip_index} 未占用，可以安全保存。"
        )
        return (conditioning, status)


NODE_CLASS_MAPPINGS = {
    "DeepWhiteH3VideoLatentLookup": DeepWhiteH3VideoLatentLookup,
    "DeepWhiteH3LatentSlotCheck": DeepWhiteH3LatentSlotCheck,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "DeepWhiteH3VideoLatentLookup": "H3 按视频查找 Latent",
    "DeepWhiteH3LatentSlotCheck": "H3 Latent 编号占用检查",
}


def _register_routes():
    try:
        from aiohttp import web
        from server import PromptServer
    except ImportError:
        return
    server = getattr(PromptServer, "instance", None)
    if server is None or getattr(_register_routes, "_done", False):
        return

    @server.routes.post("/deepwhite_h3_mc/lookup")
    async def lookup_route(request):
        data = await request.json()
        try:
            latent_path, clip_index, status = _lookup_video(
                data.get("previous_video"), data.get("source", "output")
            )
            return web.json_response(
                {
                    "ok": True,
                    "latent_path": latent_path,
                    "clip_index": clip_index,
                    "status": status,
                }
            )
        except Exception as exc:
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

    _register_routes._done = True


_register_routes()
