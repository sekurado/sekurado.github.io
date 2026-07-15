document.addEventListener("DOMContentLoaded", function () {
  var blocks = document.querySelectorAll(
    ".released-card[data-repo], .project-releases[data-repo]"
  );
  if (!blocks.length) return;

  blocks.forEach(function (block) {
    var repo = normalizeRepo(block.getAttribute("data-repo"));
    if (!repo) return;

    var isCard = block.classList.contains("released-card");
    var meta = block.querySelector(".release-meta");
    var tagsEl = block.querySelector(".release-tags");
    var downloadsEl = block.querySelector(".release-downloads");

    fetch("https://api.github.com/repos/" + repo + "/releases?per_page=5")
      .then(function (res) {
        if (!res.ok) throw new Error("GitHub API error");
        return res.json();
      })
      .then(function (releases) {
        if (meta) meta.removeAttribute("aria-busy");

        if (!releases.length) {
          if (tagsEl) {
            tagsEl.innerHTML =
              '<span class="release-empty">No releases yet</span>';
          }
          return;
        }

        renderTags(releases, tagsEl, repo, { linkTags: !isCard });
        if (!isCard) {
          renderDownloads(releases[0], downloadsEl);
        }
      })
      .catch(function () {
        if (meta) meta.removeAttribute("aria-busy");
        if (tagsEl) {
          tagsEl.innerHTML =
            '<span class="release-empty">Releases unavailable</span>';
        }
      });
  });

  function normalizeRepo(repo) {
    return repo
      .replace(/^https?:\/\/github\.com\//i, "")
      .replace(/\/$/, "")
      .trim();
  }

  function renderTags(releases, container, repo, options) {
    if (!container) return;

    options = options || {};
    var linkTags = options.linkTags === true;

    var list = document.createElement("ul");
    list.className = "post-tags release-tags-list";
    list.setAttribute("aria-label", "Releases");

    releases.forEach(function (release) {
      var item = document.createElement("li");
      var tag;

      if (linkTags) {
        tag = document.createElement("a");
        tag.className = "tag tag--link";
        tag.href = release.html_url;
        tag.rel = "noopener noreferrer";
      } else {
        tag = document.createElement("span");
        tag.className = "tag";
      }

      tag.textContent = release.tag_name;
      item.appendChild(tag);
      list.appendChild(item);
    });

    container.appendChild(list);

    var allLink = document.createElement("a");
    allLink.className = "release-all-link";
    allLink.href = "https://github.com/" + repo + "/releases";
    allLink.rel = "noopener noreferrer";
    allLink.textContent = "All releases \u2192";
    container.appendChild(allLink);
  }

  function renderDownloads(latest, container) {
    if (!container || !latest.assets || !latest.assets.length) return;

    var heading = document.createElement("p");
    heading.className = "release-downloads-label";
    heading.textContent = "Downloads (" + latest.tag_name + ")";
    container.appendChild(heading);

    var list = document.createElement("ul");
    list.className = "release-downloads-list";

    latest.assets.forEach(function (asset) {
      var item = document.createElement("li");
      var link = document.createElement("a");
      link.href = asset.browser_download_url;
      link.rel = "noopener noreferrer";
      link.textContent = asset.name;
      if (asset.size) {
        link.title = formatBytes(asset.size);
      }
      item.appendChild(link);
      if (asset.size) {
        var size = document.createElement("span");
        size.className = "release-download-size";
        size.textContent = formatBytes(asset.size);
        item.appendChild(size);
      }
      list.appendChild(item);
    });

    container.appendChild(list);
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }
});
