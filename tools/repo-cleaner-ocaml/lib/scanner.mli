(** Walks a directory tree collecting regular files, skipping [.git] and any
    other directory name the caller excludes. Purely structural -- this
    module knows nothing about hashing or redundancy, only "what files
    exist under this root." *)

type file_entry = {
  abs_path : string;  (** full filesystem path *)
  rel_path : string;  (** path relative to the scan root, used for reporting *)
  size_bytes : int;
}

val scan : ?exclude_dirs:string list -> string -> file_entry list
(** [scan ?exclude_dirs root] walks [root] recursively and returns every
    regular file found. [exclude_dirs] names (not paths) are skipped
    entirely, defaulting to [[".git"]]. Symlinks are not followed, so a
    symlink loop can't cause non-termination. *)
