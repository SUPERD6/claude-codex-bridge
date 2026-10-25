- `ccx ui` shows "Suggested notes" (H5): each pending suggestion with its kind and source, and a yes / no button
  (`POST /api/suggestion`) that writes it to shared memory or drops it. It is the page's only write and is accepted
  only from the page itself: Host and token as before, plus this server's own `Origin`, `Sec-Fetch-Site`
  same-origin when sent, and a JSON body. A snapshot (`--export`) shows `ccx mem accept N` instead. The overview's
  first line counts them. DECISIONS: narrows "phase 1 is read-only".
