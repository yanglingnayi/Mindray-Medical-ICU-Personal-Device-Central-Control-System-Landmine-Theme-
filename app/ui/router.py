import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse

router = APIRouter(tags=["超天酱地雷系核心UI-v4.2"])

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ====== 头像修复：注入脚本 ======
_AVATAR_FIX_SCRIPT = """
<script>
(function() {
  var DEFAULT_AVATAR = "https://api.dicebear.com/7.x/adventurer/svg?seed=Chouten";
  var avatarImg = document.getElementById("avatar-preview");
  if (!avatarImg) return;
  if (!avatarImg.src || avatarImg.src.indexOf("tu.jpg") >= 0 || avatarImg.src === "") {
    avatarImg.src = DEFAULT_AVATAR;
  }
  var fileInput = document.createElement("input");
  fileInput.type = "file";
  fileInput.accept = "image/*";
  fileInput.style.display = "none";
  document.body.appendChild(fileInput);
  var container = document.querySelector(".avatar-container");
  if (container) {
    container.addEventListener("click", function() { fileInput.click(); });
  }
  function cropAvatar(file, size) {
    size = size || 256;
    return new Promise(function(resolve, reject) {
      var reader = new FileReader();
      reader.onload = function(e) {
        var img = new Image();
        img.onload = function() {
          var side = Math.min(img.width, img.height);
          var sx = (img.width - side) / 2;
          var sy = (img.height - side) / 2;
          var canvas = document.createElement("canvas");
          canvas.width = size; canvas.height = size;
          var ctx = canvas.getContext("2d");
          ctx.drawImage(img, sx, sy, side, side, 0, 0, size, size);
          resolve(canvas.toDataURL("image/jpeg", 0.85));
        };
        img.onerror = reject;
        img.src = e.target.result;
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }
  function getDeviceId() {
    var sn = document.getElementById("dev_sn");
    if (sn && sn.value && sn.value.indexOf("接入中") < 0) return sn.value;
    return "";
  }
  fileInput.addEventListener("change", function() {
    var file = this.files && this.files[0];
    if (!file) return;
    if (!file.type || file.type.indexOf("image/") !== 0) { alert("请选择图片文件"); this.value = ""; return; }
    if (file.size > 8 * 1024 * 1024) { alert("图片过大（>8MB）"); this.value = ""; return; }
    cropAvatar(file, 256).then(function(cropped) {
      avatarImg.src = cropped;
      var deviceId = getDeviceId();
      if (!deviceId) {
        alert("尚未检测到监护仪 SN，暂无法保存。请等待数据接入后再上传。");
        fileInput.value = "";
        return;
      }
      return fetch("/vital/patient/avatar", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({device_id: deviceId, photo: cropped})
      }).then(function(r) { return r.json(); });
    }).then(function(result) {
      if (result && result.ok) { alert("头像保存成功！"); }
      else if (result) { alert("保存失败: " + (result.msg || "未知错误")); avatarImg.src = DEFAULT_AVATAR; }
      fileInput.value = "";
    }).catch(function(err) { alert("处理失败: " + err.message); fileInput.value = ""; });
  });
  var _origFetch = window.fetch;
  window.fetch = function(url, options) {
    var args = arguments;
    return _origFetch.apply(this, args).then(function(resp) {
      var urlStr = (resp && resp.url) ? resp.url : String(url);
      if (resp.ok && urlStr.indexOf("/vital/patient") >= 0) {
        var clone = resp.clone();
        clone.json().then(function(p) {
          if (p && p.photo && avatarImg) { avatarImg.src = p.photo; }
        });
      }
      return resp;
    });
  };
})();
</script>
"""

def _read_html(filename):
    """从 ui/ 目录读取 HTML 模板文件，并自动注入头像修复脚本"""
    with open(os.path.join(_BASE_DIR, filename), "r", encoding="utf-8") as f:
        html = f.read()
    if filename == "index.html" and "avatar-file-input" not in html:
        idx = html.rfind("</body>")
        if idx > 0:
            html = html[:idx] + _AVATAR_FIX_SCRIPT + html[idx:]
    return html


@router.get("/img/tu.jpg")
async def get_local_avatar():
    avatar_path = r"E:\OpenMonitor\img\tu.jpg"
    if os.path.exists(avatar_path):
        return FileResponse(avatar_path)
    # 文件不存在时重定向到默认头像（修复 500 错误）
    return RedirectResponse("https://api.dicebear.com/7.x/adventurer/svg?seed=Chouten")


@router.get("/img/logo.png")
async def get_favicon():
    logo_path = r"E:\OpenMonitor\img\logo.png"
    return FileResponse(logo_path, media_type="image/png")


@router.get("/audio/no.mp3")
async def get_no_signal_audio():
    audio_path = r"E:\OpenMonitor\audio\no.mp3"
    return FileResponse(audio_path, media_type="audio/mpeg")


@router.get("/audio/admin.mp3")
async def get_admin_audio():
    audio_path = r"E:\OpenMonitor\audio\adimin.mp3"
    return FileResponse(audio_path, media_type="audio/mpeg")


@router.get("/audio/end.mp3")
async def get_end_audio():
    audio_path = r"E:\OpenMonitor\audio\end.mp3"
    return FileResponse(audio_path, media_type="audio/mpeg")


@router.get("/", response_class=HTMLResponse)
async def index():
    """主监护页面（超天酱地雷系风格）"""
    return _read_html("index.html")


@router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    """患者档案管理后台（仅在此页面可修改档案信息）"""
    return _read_html("admin.html")


@router.get("/easter", response_class=HTMLResponse)
async def easter_egg():
    """彩蛋页：末音专属 — the end"""
    return _read_html("easter.html")