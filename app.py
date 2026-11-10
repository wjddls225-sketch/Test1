"""쇼핑 리스트 앱 (Streamlit).

PRD.md 기반. 3단계: 기능(FR-1 ~ FR-7) + UI 디자인 완료.

상태 변경은 모두 on_click / on_change 콜백에서 처리한다.
콜백은 스크립트 재실행 전에 실행되므로 클릭 한 번에 화면이 정확히 갱신된다.
"""

from __future__ import annotations

import html
import json
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

MAX_NAME_LEN = 50
MIN_QTY = 1
MAX_QTY = 999

# True면 data.json에 저장/불러오기 (FR-7 확장).
# 주의: Streamlit Community Cloud는 파일 시스템이 영구적이지 않다.
USE_FILE_STORAGE = False
DATA_FILE = Path(__file__).with_name("data.json")

# ---------------------------------------------------------------------------
# 저장소 (FR-7)
# ---------------------------------------------------------------------------


def _is_valid_item(obj: object) -> bool:
    return (
        isinstance(obj, dict)
        and isinstance(obj.get("id"), str)
        and isinstance(obj.get("name"), str)
        and isinstance(obj.get("quantity"), int)
        and isinstance(obj.get("checked"), bool)
    )


def load_items() -> list[dict]:
    """data.json에서 아이템을 불러온다. 파일이 없거나 손상되면 빈 목록."""
    if not DATA_FILE.exists():
        return []
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if _is_valid_item(item)]


def save_items() -> None:
    """현재 아이템을 data.json에 저장한다. 실패해도 앱은 계속 동작한다."""
    if not USE_FILE_STORAGE:
        return
    try:
        DATA_FILE.write_text(
            json.dumps(st.session_state.shopping_items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        st.session_state.storage_error = True


# ---------------------------------------------------------------------------
# 상태 관리
# ---------------------------------------------------------------------------


def init_state() -> None:
    """session_state 초기화.

    - shopping_items: list[dict]  (id, name, quantity, checked, created_at)
    - editing_id: str | None  현재 편집 중인 아이템 id
    - add_error / edit_error: 콜백에서 발생한 검증 오류 메시지
    """
    if "shopping_items" not in st.session_state:
        st.session_state.shopping_items = load_items() if USE_FILE_STORAGE else []
    st.session_state.setdefault("editing_id", None)
    st.session_state.setdefault("add_error", None)
    st.session_state.setdefault("edit_error", None)
    st.session_state.setdefault("storage_error", False)
    # 입력 위젯 초기값 (위젯에 value= 대신 여기서 지정해야 콜백에서 값을 바꿀 수 있다)
    st.session_state.setdefault("new_name", "")
    st.session_state.setdefault("new_qty", 1)


def _find_item(item_id: str) -> dict | None:
    return next((i for i in st.session_state.shopping_items if i["id"] == item_id), None)


def _validate_name(name: str) -> tuple[str | None, str | None]:
    """(정리된 이름, 오류 메시지) 반환."""
    name = (name or "").strip()
    if not name:
        return None, "아이템 이름을 입력해 주세요."
    if len(name) > MAX_NAME_LEN:
        return None, f"아이템 이름은 {MAX_NAME_LEN}자 이내로 입력해 주세요."
    return name, None


def _validate_qty(quantity: int | float | None) -> tuple[int | None, str | None]:
    """(정수 수량, 오류 메시지) 반환. 범위 밖이면 조용히 바꾸지 않고 오류로 알린다."""
    error = f"수량은 {MIN_QTY}~{MAX_QTY} 사이로 입력해 주세요."
    if quantity is None or isinstance(quantity, bool):
        return None, error
    try:
        q = int(quantity)
    except (TypeError, ValueError):
        return None, error
    if q != quantity or not MIN_QTY <= q <= MAX_QTY:
        return None, error
    return q, None


def add_item(name: str, quantity: int = 1) -> bool:
    """새 아이템을 목록 맨 아래에 추가한다. (FR-1) 성공 여부 반환."""
    clean, error = _validate_name(name)
    if not error:
        qty, error = _validate_qty(quantity)
    if error:
        st.session_state.add_error = error
        return False
    st.session_state.shopping_items.append(
        {
            "id": str(uuid.uuid4()),
            "name": clean,
            "quantity": qty,
            "checked": False,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    st.session_state.add_error = None
    save_items()
    return True


def update_item(item_id: str, name: str, quantity: int) -> bool:
    """아이템의 이름과 수량을 수정하고 편집 모드를 종료한다. (FR-2)"""
    item = _find_item(item_id)
    if item is None:
        st.session_state.editing_id = None
        return False
    clean, error = _validate_name(name)
    if not error:
        qty, error = _validate_qty(quantity)
    if error:
        st.session_state.edit_error = error
        return False
    item["name"] = clean
    item["quantity"] = qty
    st.session_state.editing_id = None
    st.session_state.edit_error = None
    save_items()
    return True


def delete_item(item_id: str) -> None:
    """아이템을 삭제한다. 편집 중인 아이템이면 editing_id도 초기화한다. (FR-3)"""
    st.session_state.shopping_items = [i for i in st.session_state.shopping_items if i["id"] != item_id]
    if st.session_state.editing_id == item_id:
        st.session_state.editing_id = None
        st.session_state.edit_error = None
    save_items()


def toggle_item(item_id: str) -> None:
    """아이템의 체크(구매 완료) 상태를 체크박스 값과 동기화한다. (FR-4)"""
    item = _find_item(item_id)
    if item is None:
        return
    item["checked"] = bool(st.session_state.get(f"chk_{item_id}", not item["checked"]))
    save_items()


def clear_checked() -> None:
    """체크된 아이템을 모두 삭제한다. (FR-6)"""
    removed = {i["id"] for i in st.session_state.shopping_items if i["checked"]}
    st.session_state.shopping_items = [i for i in st.session_state.shopping_items if not i["checked"]]
    if st.session_state.editing_id in removed:
        st.session_state.editing_id = None
        st.session_state.edit_error = None
    save_items()


# ---------------------------------------------------------------------------
# 콜백 (위젯 값 → 상태 함수)
# ---------------------------------------------------------------------------


def _on_add() -> None:
    name = st.session_state.get("new_name", "")
    if add_item(name, st.session_state.get("new_qty", 1)):
        # 성공했을 때만 입력칸을 비운다 (실패 시 입력값 유지)
        st.session_state.new_name = ""
        st.session_state.new_qty = 1
        st.toast(f"'{name.strip()}' 추가됨", icon="✅")


def _on_delete(item_id: str) -> None:
    item = _find_item(item_id)
    delete_item(item_id)
    if item is not None:
        st.toast(f"'{item['name']}' 삭제됨", icon="🗑️")


def _on_clear_checked() -> None:
    count = sum(1 for i in st.session_state.shopping_items if i["checked"])
    clear_checked()
    if count:
        st.toast(f"체크된 항목 {count}개 삭제됨", icon="🧹")


def _on_start_edit(item_id: str) -> None:
    item = _find_item(item_id)
    if item is None:
        return
    # 편집 위젯의 초기값을 현재 아이템 값으로 설정 (다른 아이템 편집 중이었다면 교체)
    st.session_state[f"edit_name_{item_id}"] = item["name"]
    st.session_state[f"edit_qty_{item_id}"] = item["quantity"]
    st.session_state.editing_id = item_id
    st.session_state.edit_error = None


def _on_save_edit(item_id: str) -> None:
    update_item(
        item_id,
        st.session_state.get(f"edit_name_{item_id}", ""),
        st.session_state.get(f"edit_qty_{item_id}", 1),
    )


def _on_cancel_edit() -> None:
    st.session_state.editing_id = None
    st.session_state.edit_error = None


# ---------------------------------------------------------------------------
# 화면 렌더링
# ---------------------------------------------------------------------------

# 최소한의 CSS. 색은 테마 변수/opacity만 사용해 라이트·다크 모두 대응한다.
CSS = """
<style>
.block-container { max-width: 720px; padding-top: 2.5rem; }

/* 아이템 이름: 긴 이름도 줄바꿈되어 레이아웃이 깨지지 않게 */
.item-name { overflow-wrap: anywhere; word-break: break-word; line-height: 1.4; }
.item-name.done { text-decoration: line-through; opacity: 0.45; }
.item-qty { font-size: 0.85rem; opacity: 0.6; white-space: nowrap; }
.item-qty.done { opacity: 0.35; }
.summary-text { font-size: 0.95rem; }
.summary-text b { font-size: 1.05rem; }

/* 아이콘 버튼: 여백 축소 */
.st-key-item_list button, .st-key-add_row button { padding: 0.25rem 0.55rem; min-height: 2.4rem; }
.st-key-add_row button, .st-key-add_row button p { white-space: nowrap; }

/* 모바일: Streamlit 기본은 640px 미만에서 컬럼을 세로로 쌓는다.
   목록 행과 입력 행은 가로 배치를 유지한다. */
@media (max-width: 640px) {
  .st-key-item_list [data-testid="stHorizontalBlock"],
  .st-key-add_row [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    gap: 0.35rem !important;
  }
  .st-key-item_list [data-testid="stColumn"],
  .st-key-add_row [data-testid="stColumn"] {
    min-width: 0 !important;
  }
  .st-key-item_list button, .st-key-add_row button { padding: 0.2rem 0.4rem; }
  /* 추가 버튼 칸은 내용 폭만큼, 이름 칸이 나머지를 차지 */
  .st-key-add_row [data-testid="stColumn"]:last-child {
    flex: 0 0 auto !important; width: auto !important;
  }
  .st-key-add_row [data-testid="stColumn"]:first-child { flex: 1 1 0 !important; }
  .st-key-add_row [data-testid="stColumn"]:nth-child(2) { flex: 0 0 5.5rem !important; }
  /* 좁은 화면에서는 추가 버튼의 아이콘을 숨겨 글자가 줄바꿈되지 않게 */
  .st-key-add_row button [data-testid="stIconEmoji"],
  .st-key-add_row button span[aria-hidden="true"] { display: none; }
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 1.5rem; }
}
</style>
"""


def render_input_form() -> None:
    """아이템 이름/수량 입력 폼과 추가 버튼. (FR-1)"""
    with st.form("add_form", border=True):
        with st.container(key="add_row"):
            c_name, c_qty, c_btn = st.columns([5, 2, 1.3], vertical_alignment="bottom")
            c_name.text_input("아이템 이름", key="new_name", max_chars=MAX_NAME_LEN,
                              placeholder="살 물건을 입력하세요 (예: 우유)")
            # min/max를 위젯에 걸면 범위 밖 값이 경고 없이 버려지므로 서버에서 검증한다
            c_qty.number_input("수량", key="new_qty", step=1,
                               help=f"{MIN_QTY}~{MAX_QTY}개")
            c_btn.form_submit_button("추가", icon="➕", type="primary",
                                     on_click=_on_add, use_container_width=True)
    if st.session_state.add_error:
        st.warning(st.session_state.add_error, icon="⚠️")
        st.session_state.add_error = None
    if st.session_state.storage_error:
        st.error("data.json 저장에 실패했습니다.")
        st.session_state.storage_error = False


def render_summary() -> None:
    """전체/완료 개수와 진행률 표시. (FR-5)"""
    items = st.session_state.shopping_items
    total = len(items)
    done = sum(1 for i in items if i["checked"])
    ratio = done / total if total else 0.0
    st.markdown(
        f'<div class="summary-text">전체 <b>{total}</b>개 · 완료 <b>{done}</b>개'
        f' · 남은 <b>{total - done}</b>개</div>',
        unsafe_allow_html=True,
    )
    st.progress(ratio, text=f"진행률 {round(ratio * 100)}%")


def _render_edit_row(item: dict) -> None:
    item_id = item["id"]
    cols = st.columns([5, 2.4, 0.9, 0.9], vertical_alignment="center")
    cols[0].text_input("이름", key=f"edit_name_{item_id}", max_chars=MAX_NAME_LEN,
                       label_visibility="collapsed")
    cols[1].number_input("수량", key=f"edit_qty_{item_id}", step=1,
                         label_visibility="collapsed")
    cols[2].button("💾", key=f"save_{item_id}", help="저장", type="primary",
                   on_click=_on_save_edit, args=(item_id,))
    cols[3].button("↩️", key=f"cancel_{item_id}", help="취소",
                   on_click=_on_cancel_edit)
    if st.session_state.edit_error:
        st.warning(st.session_state.edit_error, icon="⚠️")


def _render_view_row(item: dict) -> None:
    item_id = item["id"]
    done = " done" if item["checked"] else ""
    cols = st.columns([0.6, 5, 1.1, 0.9, 0.9], vertical_alignment="center")
    cols[0].checkbox("구매 완료", key=f"chk_{item_id}", value=item["checked"],
                     on_change=toggle_item, args=(item_id,),
                     label_visibility="collapsed")
    cols[1].markdown(f'<div class="item-name{done}">{html.escape(item["name"])}</div>',
                     unsafe_allow_html=True)
    cols[2].markdown(f'<div class="item-qty{done}">x{item["quantity"]}</div>',
                     unsafe_allow_html=True)
    cols[3].button("✏️", key=f"edit_{item_id}", help="수정",
                   on_click=_on_start_edit, args=(item_id,))
    cols[4].button("🗑️", key=f"del_{item_id}", help="삭제",
                   on_click=_on_delete, args=(item_id,))


def render_item_list() -> None:
    """아이템 목록: 체크박스 | 이름 | 수량 | 수정 | 삭제. (FR-2~4)"""
    items = st.session_state.shopping_items
    if not items:
        st.info("목록이 비어 있습니다. 아이템을 추가해 보세요.", icon="🧺")
        return
    with st.container(border=True, key="item_list"):
        for idx, item in enumerate(items):
            if idx:
                st.markdown('<hr style="margin:0.1rem 0;opacity:0.4">',
                            unsafe_allow_html=True)
            if item["id"] == st.session_state.editing_id:
                _render_edit_row(item)
            else:
                _render_view_row(item)


def render_footer() -> None:
    """체크된 항목 일괄 삭제 버튼. (FR-6)"""
    has_checked = any(i["checked"] for i in st.session_state.shopping_items)
    st.button("체크된 항목 지우기", key="clear_checked", icon="🧹",
              on_click=_on_clear_checked, disabled=not has_checked,
              help="구매 완료로 체크한 항목을 모두 삭제합니다")


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒")
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)

    st.title("🛒 쇼핑 리스트")
    render_input_form()
    render_summary()
    render_item_list()
    render_footer()


if __name__ == "__main__":
    main()
