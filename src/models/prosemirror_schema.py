from prosemirror.model import Schema

def get_color_from_style(style_str):
    if not style_str:
        return None
    styles = [s.strip() for s in style_str.split(';') if s.strip()]
    for style in styles:
        if style.startswith('color:'):
            return style.split(':')[1].strip()
    return None

schema = Schema({
    "nodes": {
        "doc": {
            "content": "block+"
        },
        "paragraph": {
            "content": "inline*",
            "group": "block",
            "parseDOM": [{"tag": "p"}],
            "toDOM": lambda node: ["p", 0]
        },
        "heading": {
            "attrs": {"level": {"default": 1}},
            "content": "inline*",
            "group": "block",
            "defining": True,
            "parseDOM": [
                {"tag": "h1", "attrs": {"level": 1}},
                {"tag": "h2", "attrs": {"level": 2}},
                {"tag": "h3", "attrs": {"level": 3}},
                {"tag": "h4", "attrs": {"level": 4}},
                {"tag": "h5", "attrs": {"level": 5}},
                {"tag": "h6", "attrs": {"level": 6}},
            ],
            "toDOM": lambda node: [f"h{node.attrs['level']}", 0]
        },
        "text": {
            "group": "inline"
        },
        "bulletList": {
            "content": "listItem+",
            "group": "block",
            "parseDOM": [{"tag": "ul"}],
            "toDOM": lambda node: ["ul", 0]
        },
        "orderedList": {
            "attrs": {"order": {"default": 1}},
            "content": "listItem+",
            "group": "block",
            "parseDOM": [{
                "tag": "ol",
                "getAttrs": lambda dom: {
                    "order": int(dom.get("start")) if dom.get("start") is not None else 1
                }
            }],
            "toDOM": lambda node: [
                "ol",
                {"start": None if node.attrs["order"] == 1 else node.attrs["order"]},
                0
            ]
        },
        "listItem": {
            "content": "paragraph block*",
            "defining": True,
            "parseDOM": [{"tag": "li"}],
            "toDOM": lambda node: ["li", 0]
        },
        "taskList": {
            "group": "block",
            "content": "taskItem+",
            "parseDOM": [{"tag": "ul[data-type='taskList']"}],
            "toDOM": lambda node: ["ul", {"data-type": "taskList"}, 0]
        },
        "taskItem": {
            "content": "paragraph block*",
            "defining": True,
            "attrs": {"checked": {"default": False}},
            "parseDOM": [{
                "tag": "li",
                "getAttrs": lambda dom: {
                    "checked": dom.get("data-checked") == "true"
                }
            }],
            "toDOM": lambda node: [
                "li",
                {"data-checked": "true" if node.attrs["checked"] else "false"},
                0
            ]
        },
        "blockquote": {
            "content": "block+",
            "group": "block",
            "defining": True,
            "parseDOM": [{"tag": "blockquote"}],
            "toDOM": lambda node: ["blockquote", 0]
        },
        "horizontalRule": {
            "group": "block",
            "parseDOM": [{"tag": "hr"}],
            "toDOM": lambda node: ["hr"]
        },
        "hardBreak": {
            "inline": True,
            "group": "inline",
            "selectable": False,
            "parseDOM": [{"tag": "br"}],
            "toDOM": lambda node: ["br"]
        }
    },
    "marks": {
        "bold": {
            "parseDOM": [
                {"tag": "strong"},
                {
                    "tag": "b",
                    "getAttrs": lambda dom: None if "font-weight: normal" in dom.get("style", "").lower() else False
                }
            ],
            "toDOM": lambda mark, inline: ["strong", 0] 
        },
        "italic": {
            "parseDOM": [{"tag": "i"}, {"tag": "em"}],
            "toDOM": lambda mark, inline: ["em", 0]
        },
        "code": {
            "parseDOM": [{"tag": "code"}],
            "toDOM": lambda mark, inline: ["code", 0]
        },
        "strike": {
            "parseDOM": [{"tag": "s"}, {"tag": "del"}],
            "toDOM": lambda mark, inline: ["s", 0]
        },
        "textStyle": {
            "attrs": {
                "color": {"default": None}
            },
            "parseDOM": [{
                "tag": "span",
                "getAttrs": lambda dom: {"color": color} if (color := get_color_from_style(dom.get("style"))) else False
            }],
            "toDOM": lambda mark, inline: (
                ["span", {"style": f"color: {mark.attrs['color']}"}, 0] 
                if mark.attrs.get("color") 
                else ["span", 0]
            )
        }
    }
})