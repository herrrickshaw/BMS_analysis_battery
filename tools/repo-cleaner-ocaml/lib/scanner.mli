(** Walks a directory tree collecting regular files, skipping [.git] and any
    other directory name the caller excludes. Purely structural -- this
    module knows nothing about hashing or redundancy, only "what files
    exist under this root." *)

type file_entry = {
  abs_path : string;  (** full filesystem path *)
  rel_path : string;  (** path relative to the scan root, used for reporting *)
  size_bytes : int;
}

val default_exclude_dirs : string list
(** [".git"; "_build"; "node_modules"; ".venv"; "venv"; "__pycache__";
    "dist"; "target"] -- common build-output/dependency directories across
    several ecosystems. This is a fixed denylist, NOT real [.gitignore]
    parsing: a project with an unusual ignored directory name will still
    have it scanned. It exists because {!scan} operates on the filesystem
    directly, not git's index -- a build artifact under one of these names
    can otherwise be mistaken for source (this is not hypothetical: an
    early run of this tool against its own [_build/] output proposed
    keeping a compiled copy of a source file and deleting the real one,
    caught in a dry run before anything was actually removed). *)

val scan : ?exclude_dirs:string list -> string -> file_entry list
(** [scan ?exclude_dirs root] walks [root] recursively and returns every
    regular file found. [exclude_dirs] names (not paths) are skipped
    entirely, defaulting to {!default_exclude_dirs}. Symlinks are not
    followed, so a symlink loop can't cause non-termination. *)
