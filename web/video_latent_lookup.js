import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";

app.registerExtension({
  name: "deepwhite.h3.mc.video_latent_lookup",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "DeepWhiteH3VideoLatentLookup") return;

    const original = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = original?.apply(this, arguments);
      const videoWidget = this.widgets?.find((widget) => widget.name === "previous_video");
      if (videoWidget) videoWidget.label = "从下拉框选择视频";

      const fitText = (ctx, text, maxWidth) => {
        const value = String(text || "");
        if (ctx.measureText(value).width <= maxWidth) return value;
        let shortened = value;
        while (shortened.length > 1 && ctx.measureText(`${shortened}…`).width > maxWidth) {
          shortened = shortened.slice(0, -1);
        }
        return `${shortened}…`;
      };

      const status = {
        name: "查询结果",
        type: "deepwhite_h3_lookup_status",
        options: { serialize: false },
        primary: "尚未查询",
        detail: "上传本地视频，或从下拉框选择视频",
        computeSize: (width) => [width, 62],
        draw: (ctx, node, width, y) => {
          const left = 10;
          const boxWidth = width - 20;
          ctx.save();
          ctx.beginPath();
          ctx.roundRect(left, y + 3, boxWidth, 56, 8);
          ctx.fillStyle = "#17241f";
          ctx.fill();
          ctx.strokeStyle = "#456656";
          ctx.lineWidth = 1;
          ctx.stroke();
          ctx.font = "12px sans-serif";
          ctx.fillStyle = "#7fa890";
          ctx.fillText("查询结果", left + 12, y + 21);
          ctx.font = "14px sans-serif";
          ctx.fillStyle = "#eef6f1";
          ctx.fillText(fitText(ctx, status.primary, boxWidth - 24), left + 12, y + 40);
          ctx.font = "11px sans-serif";
          ctx.fillStyle = "#91a89c";
          ctx.fillText(fitText(ctx, status.detail, boxWidth - 24), left + 12, y + 54);
          ctx.restore();
        },
      };
      this.addCustomWidget(status);

      const setStatus = (primary, detail = "") => {
        status.primary = primary;
        status.detail = detail;
        this.setDirtyCanvas(true, true);
      };

      let uploadedSelection = null;

      const showResult = async (previousVideo, source) => {
        setStatus("正在查询……", source === "input" ? "正在读取上传视频的元数据" : "正在读取输出目录视频");
        try {
          const response = await api.fetchApi("/deepwhite_h3_mc/lookup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ previous_video: previousVideo, source }),
          });
          const data = await response.json();
          if (!response.ok || !data.ok) throw new Error(data.error || "查询失败");
          setStatus(`Clip 编号：${data.clip_index}`, data.latent_path);
        } catch (error) {
          setStatus("未找到对应编号", error?.message || error);
        }
      };

      const queryButton = this.addWidget("button", "查询", null, async () => {
        if (uploadedSelection) {
          await showResult(uploadedSelection.path, "input");
        } else {
          await showResult(videoWidget?.value, "output");
        }
      });

      const uploadButton = this.addWidget("button", "上传本地视频", null, async () => {
        const picker = document.createElement("input");
        picker.type = "file";
        picker.accept = "video/mp4,video/quicktime,video/x-matroska,video/webm,video/x-msvideo,.mp4,.mov,.mkv,.webm,.avi";
        picker.onchange = async () => {
          const file = picker.files?.[0];
          if (!file) return;
          setStatus("正在上传……", file.name);
          try {
            const body = new FormData();
            body.append("image", file, file.name);
            body.append("type", "input");
            body.append("subfolder", "deepwhite_h3_mc_lookup");
            const response = await api.fetchApi("/upload/image", {
              method: "POST",
              body,
            });
            const data = await response.json();
            if (!response.ok || !data?.name) {
              throw new Error(data?.error || `上传失败（HTTP ${response.status}）`);
            }
            const subfolder = String(data.subfolder || "").replace(/\\/g, "/").replace(/^\/+|\/+$/g, "");
            const uploadedVideo = subfolder ? `${subfolder}/${data.name}` : data.name;
            uploadedSelection = { path: uploadedVideo, name: data.name };
            setStatus("已上传，等待查询", `${data.name}｜请点击“查询”`);
          } catch (error) {
            uploadedSelection = null;
            setStatus("上传失败", error?.message || error);
          }
        };
        picker.click();
      });

      if (videoWidget) {
        const originalVideoCallback = videoWidget.callback;
        videoWidget.callback = function (value) {
          uploadedSelection = null;
          setStatus("已选择输出目录视频", "请点击“查询”读取 Clip 编号");
          return originalVideoCallback?.apply(this, arguments);
        };
      }

      uploadButton.color = "#2f7658";
      queryButton.color = "#3e6685";

      const orderedWidgets = [uploadButton, videoWidget, queryButton, status].filter(Boolean);
      const otherWidgets = (this.widgets || []).filter(
        (widget) => !orderedWidgets.includes(widget)
      );
      this.widgets.splice(0, this.widgets.length, ...orderedWidgets, ...otherWidgets);
      this.setSize([440, 220]);
      return result;
    };
  },
});
