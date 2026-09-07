# v3.59.2 — Map and campaign-record reliability

- Lost, inactive, retired and abandoned claims no longer repaint the atlas. Claim status survives normalization/save reload.
- New ownership is not overwritten by stale location details. Explicit newer location updates still synchronize; similarly named neighboring locations no longer match by substring.
- Queued travel estimates chain from the preceding destination. Empty or ambiguous destinations no longer silently select an arbitrary landmark; detailed origins prefer the longest matching landmark.
- Correct the GM has an optional local evidence review of the last 500 campaign records, capped at 20 suggestions. Explicit acquisitions and conquests are offered for review, never applied automatically. Historical control is not assumed current; later losses must be checked.
- An existing territory/holding controller can be corrected through the same preview-and-confirm screen. Existing claim size is preserved, unknown borders are rejected, and changed ownership invalidates stale previews.

No new AI calls, destinations or timeline dates. The review is a conservative phrase matcher, not an exhaustive interpretation of every old Chronicle. Ability suggestions do not invent stat boosts or reconstruct world-specific special profiles. Review the details before confirming. The larger living-world update remains separate.
