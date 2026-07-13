(** Classifies branches by how stale they are relative to a base branch --
    the same ahead/behind analysis used earlier in this project by hand via
    plain [git rev-list --count], now a real, tested part of the tool
    instead of a one-off shell loop. *)

type branch_info = {
  name : string;
  ahead : int;  (** commits on [name] not reachable from the base ref *)
  behind : int;  (** commits on the base ref not reachable from [name] *)
  last_commit_date : string;  (** ISO 8601, from the branch tip *)
  last_commit_subject : string;
}

val analyze : repo_dir:string -> base_ref:string -> string list -> branch_info list
(** [analyze ~repo_dir ~base_ref branches] runs `git` inside [repo_dir] (which
    must already be a clone containing every ref in [branches] and
    [base_ref]) to compute ahead/behind and last-commit metadata for each
    branch. A branch that can't be resolved (typo, not fetched) is silently
    skipped rather than raising -- one bad ref shouldn't abort analysis of
    the rest. Sorted by [behind] descending, so the stalest branches are
    reported first. *)

val classify : branch_info -> [ `Likely_stale | `Recent | `Merged ]
(** Heuristic label: [`Merged] when [ahead = 0] (nothing on the branch isn't
    already on the base — safe to delete outright), [`Likely_stale] when
    [behind] is large relative to typical repo activity (more than 50
    commits, a threshold callers can't currently override — see the
    [classify] implementation if that needs to become a parameter),
    otherwise [`Recent]. This is a starting triage, not a delete order: even
    a [`Likely_stale] branch may hold work worth reviewing before removal. *)
