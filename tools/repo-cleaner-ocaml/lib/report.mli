(** Renders findings from the other modules into one Markdown report. This
    module only formats -- it never deletes a file or a branch. Turning a
    finding into an action is a separate, explicit, human-reviewed step. *)

val render :
  root:string ->
  duplicate_groups:Duplicate_finder.group list ->
  name_clusters:Name_clusterer.cluster list ->
  branches:Branch_analyzer.branch_info list ->
  ?data_duplicate_groups:Duplicate_finder.group list ->
  ?annotate:(Scanner.file_entry -> string option) ->
  unit ->
  string
(** [data_duplicate_groups] (default: none) are duplicates found via
    {!Data_manifest} -- LFS pointer [oid] equality or a data file's raw
    content hash -- reported in their own section since "identical
    dataset checked into two repos" reads differently from "identical
    script pasted into two repos."

    [annotate] (default: none), when given, is called once per file
    listed in a duplicate group or name cluster; a [Some s] result is
    appended after that file's path. This module doesn't compute recency
    or size itself -- it has no opinion on what an annotation should say,
    it just prints whatever the caller hands it. See how the CLI uses this
    to mark, per cross-repo duplicate group, which copy's repo touched it
    most recently. *)
