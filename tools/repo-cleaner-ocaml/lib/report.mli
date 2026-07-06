(** Renders findings from the other modules into one Markdown report. This
    module only formats -- it never deletes a file or a branch. Turning a
    finding into an action is a separate, explicit, human-reviewed step. *)

val render :
  root:string ->
  duplicate_groups:Duplicate_finder.group list ->
  name_clusters:Name_clusterer.cluster list ->
  branches:Branch_analyzer.branch_info list ->
  string
