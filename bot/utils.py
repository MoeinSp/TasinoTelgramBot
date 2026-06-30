import ast
import re

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

MAX_EXPR_LEN = 50
MAX_NUMBER = 10 ** 9
MAX_RESULT = 10 ** 12


def normalize_numbers(text: str) -> str:
    return text.translate(_PERSIAN_DIGITS)


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _eval_ast(node):
    if isinstance(node, ast.Constant):
        if abs(node.value) > MAX_NUMBER:
            raise ValueError("عدد خیلی بزرگ")
        return node.value
    if isinstance(node, ast.BinOp):
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        ops = {
            ast.Add: lambda a, b: a + b,
            ast.Sub: lambda a, b: a - b,
            ast.Mult: lambda a, b: a * b,
            ast.Div: lambda a, b: a / b if b else (_ for _ in ()).throw(ZeroDivisionError()),
        }
        op = ops.get(type(node.op))
        if op is None:
            raise ValueError("عملیات مجاز نیست")
        return op(left, right)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_ast(node.operand)
    raise ValueError("بیان مجاز نیست")


def safe_calc(expr: str) -> float | None:
    expr = normalize_numbers(expr).strip()
    if len(expr) > MAX_EXPR_LEN:
        return None
    try:
        tree = ast.parse(expr, mode="eval")
        result = _eval_ast(tree.body)
        if abs(result) > MAX_RESULT:
            return None
        return result
    except Exception:
        return None


def contains_link(text: str) -> bool:
    return bool(re.search(r"(https?://|t\.me/|@\w+)", text, re.IGNORECASE))


def contains_username(text: str) -> bool:
    return bool(re.search(r"@\w{3,}", text))


def contains_forbidden_word(text: str, word_list: list[str]) -> bool:
    low = text.lower()
    return any(w in low for w in word_list)
