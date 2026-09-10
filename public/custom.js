(function () {
  function addRegisterLink() {
    if (document.getElementById("plantlik-register-link")) return;
    if (!location.pathname.startsWith("/login") && location.pathname !== "/") return;

    var form = document.querySelector("form");
    if (!form) return;

    var p = document.createElement("p");
    p.id = "plantlik-register-link";
    p.style.marginTop = "1rem";
    p.style.fontSize = "0.875rem";
    p.style.textAlign = "center";
    p.innerHTML = 'Hesabın yok mu? <a href="/register" style="color:#c98a4f;">Kayıt ol</a>';
    form.parentElement.appendChild(p);
  }

  var observer = new MutationObserver(addRegisterLink);
  observer.observe(document.body, { childList: true, subtree: true });
  addRegisterLink();
})();
