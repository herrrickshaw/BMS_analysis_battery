(** Content hashing for exact-duplicate detection.

    MD5 (via the stdlib [Digest] module) rather than a cryptographic hash --
    this tool is comparing files a human will still review before anything
    is removed, not defending against an adversary constructing a
    collision, so stdlib-only (no external dependency) is the right
    trade-off here. *)

val file_hash : string -> string
(** [file_hash path] returns the MD5 digest of the file at [path], as a hex
    string. Raises [Sys_error] if the file can't be read. *)
