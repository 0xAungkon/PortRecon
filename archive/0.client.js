// Go to https://lite.ip2location.com/nigeria-ip-address-ranges
// Open the browser console and paste this code to download the IP ranges as a JSON file.

document.querySelectorAll(".text-end").forEach(e => e.remove());

const IPS = [];

document.querySelectorAll("tr").forEach(tr => {
  const td = tr.querySelectorAll("td");
  if (td.length >= 2) {
    IPS.push(`${td[0].textContent.trim()}-${td[1].textContent.trim()}`);
  }
});

const blob = new Blob([JSON.stringify(IPS, null, 2)], { type: "application/json" });
const url = URL.createObjectURL(blob);
const a = document.createElement("a");
a.href = url;
a.download = location.pathname.replace("/","").replace("-ip-address-ranges","") + ".json";
a.click();
URL.revokeObjectURL(url);