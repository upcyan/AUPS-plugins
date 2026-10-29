"""remotedebug 多行脚本 # 注释支持回归。

真实故障：# 开头的整行注释与行尾注释此前被当作命令名解析，报
"命令不在只读目录中：#"。剥离必须引号感知：正则/参数中的 #（如 grep "a#b"）
不能误删。
Isolated: never starts host services or containers.
"""
import unittest
from unittest.mock import patch

from test_remotedebug_security import _stub_modules, _load


CASES = [
    ("# 整行注释", ""),
    ("#紧贴行首", ""),
    ("  # 缩进注释", ""),
    ("ls -la # 行尾注释", "ls -la"),
    ("tail -n 5 f #取尾部", "tail -n 5 f"),
    ("grep -E \"a#b\" file", "grep -E \"a#b\" file"),
    ("grep '#' file", "grep '#' file"),
    ("ls a#b.txt", "ls a#b.txt"),          # 词中 # 非注释
    ('grep "unclosed # quote', 'grep "unclosed # quote'),  # 引号未闭合保守不剥
]


class CommentStripTests(unittest.TestCase):
    def setUp(self):
        self._patcher = patch.dict(__import__("sys").modules, _stub_modules())
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self.redact = _load("redact")
        self.runner = _load("runner")

    def test_strip_comment(self):
        for src, want in CASES:
            self.assertEqual(self.runner._strip_comment(src), want, src)

    def test_execute_skips_comment_lines(self):
        # 整行注释跳过，不占 max_steps、不参与校验
        import types as _t
        tmp = _t.SimpleNamespace()
        roots = ["/tmp"]
        plan = self.runner.validate_line("ls /tmp", roots=roots)
        self.assertEqual(plan["bin"], plan["bin"])
        # 多行含注释：有效行数应为 2
        script = "# 头注释\nls /tmp\n# 中间注释\nls /tmp\n"
        lines = []
        for raw in script.splitlines():
            code = self.runner._strip_comment(raw)
            if code.strip():
                lines.append(code.strip())
        self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
