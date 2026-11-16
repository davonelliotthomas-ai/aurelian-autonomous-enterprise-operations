(function () {
  "use strict";
  const escape = (value) => value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);
  function inline(text) {
    return escape(text).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  }
  function slug(text) {
    return text.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim().replace(/ +/g, "-");
  }
  function renderMarkdown(markdown) {
    const lines = markdown.replace(/\r\n/g, "\n").split("\n");
    const output = [];
    let paragraph = [], list = null, code = false, fenced = [];
    function flushParagraph() {
      if (paragraph.length) { output.push("<p>" + inline(paragraph.join(" ")) + "</p>"); paragraph = []; }
    }
    function flushList() { if (list) { output.push("</" + list + ">"); list = null; } }
    for (const line of lines) {
      if (line.startsWith("~~~")) {
        flushParagraph(); flushList();
        if (code) { output.push("<pre><code>" + escape(fenced.join("\n")) + "</code></pre>"); fenced = []; }
        code = !code; continue;
      }
      if (code) { fenced.push(line); continue; }
      if (!line.trim()) { flushParagraph(); flushList(); continue; }
      const heading = /^(#{1,3})\s+(.+)$/.exec(line);
      if (heading) {
        flushParagraph(); flushList();
        const level = heading[1].length;
        const title = heading[2].replace(/\*\*/g, "");
        output.push("<h" + level + ' id="' + slug(title) + '">' + inline(heading[2]) + "</h" + level + ">");
        continue;
      }
      if (line.startsWith("> ")) {
        flushParagraph(); flushList();
        output.push("<blockquote><p>" + inline(line.slice(2)) + "</p></blockquote>");
        continue;
      }
      const listItem = /^(?:- |\d+\.\s+)(.+)$/.exec(line);
      if (listItem) {
        flushParagraph();
        const kind = line.startsWith("- ") ? "ul" : "ol";
        if (kind !== list) { flushList(); list = kind; output.push("<" + list + ">"); }
        output.push("<li>" + inline(listItem[1]) + "</li>");
        continue;
      }
      flushList(); paragraph.push(line.trim());
    }
    flushParagraph(); flushList();
    return output.join("\n");
  }
  fetch("./ENGINEERING_WALKTHROUGH.md").then((res) => {
    if (!res.ok) throw Error("Walkthrough source unavailable");
    return res.text();
  }).then((text) => {
    document.getElementById("article").innerHTML = renderMarkdown(text);
    const items = [...document.querySelectorAll(".reading-article h2")]
      .filter((heading) => /00:|01:|02:|04:|05:|07:|08:|10:|11:|12:|14:|One-minute|Explain it|Engineer interview|Rehearsal/.test(heading.textContent));
    document.getElementById("toc-items").innerHTML = items.map((heading) =>
      '<a href="#' + heading.id + '">' + escape(heading.textContent.replace(/ — .+$/, "")) + "</a>"
    ).join("");
  }).catch((error) => {
    document.getElementById("article").textContent = "Unable to load walkthrough: " + error.message;
  });
})();
