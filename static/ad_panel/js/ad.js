document.addEventListener("DOMContentLoaded", () => {
  // سوپر بمب در فرم خارج از برنامه
  const customForm = document.getElementById("custom-form");
  if (customForm) {
    const mode = document.getElementById("custom-mode");
    const joinBox = document.getElementById("custom-join-box");
    const sync = () => {
      if (joinBox) joinBox.style.display = mode && mode.value === "super" ? "" : "none";
    };
    if (mode) mode.addEventListener("change", sync);
    sync();
  }

  // ویرایشگر برنامه ساعت
  const rows = document.getElementById("schedule-rows");
  const addBtn = document.getElementById("add-row");
  const tpl = document.getElementById("row-template");
  if (rows && addBtn && tpl) {
    addBtn.addEventListener("click", () => {
      rows.appendChild(tpl.content.cloneNode(true));
    });
    rows.addEventListener("click", (e) => {
      const btn = e.target.closest(".row-del");
      if (!btn) return;
      const row = btn.closest(".schedule-row");
      if (rows.querySelectorAll(".schedule-row").length <= 1) return;
      row.remove();
    });
  }
});
