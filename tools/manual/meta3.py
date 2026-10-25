import sys

sys.path.insert(0, r"D:\vidlens\vidlens")
import vidlens_extra as E  # noqa: E402

URLS = [
    "https://www.bilibili.com/video/BV17LHw64EMX/",
    "https://www.bilibili.com/video/BV1oUJB6QEL5/",
    "https://www.bilibili.com/video/BV1Kwnr61EeS/",
]

for u in URLS:
    bv = E.bvid_of(u)
    try:
        v = E._get_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bv}")
    except Exception as e:
        print(bv, "FAILED", e)
        continue
    if v.get("code") != 0:
        print(bv, "code", v.get("code"), v.get("message"))
        continue
    d = v["data"]
    st = d.get("stat") or {}
    print("=" * 70)
    print(bv, "|", d.get("title"))
    print("  owner:", (d.get("owner") or {}).get("name"),
          "| dur:", d.get("duration"), "s | tname:", d.get("tname"),
          "| pubdate:", d.get("pubdate"))
    print("  stat:", {k: st.get(k) for k in ("view", "danmaku", "reply", "like", "coin", "favorite", "share")})
    print("  desc:", (d.get("desc") or "")[:200].replace("\n", " / "))
