(** Catalogs data files (parquet/db/csv/json/xlsx/gz) across the scanned
    roots WITHOUT downloading real Git LFS content -- an LFS-tracked file
    checked out with smudging skipped sits on disk as a small plain-text
    pointer (`version .../oid sha256:.../size N`), and that pointer's
    [oid] already tells you, for free, whether two files point at
    byte-identical underlying data. This is what makes "compile every data
    source and find redundancy" tractable without pulling gigabytes of
    real parquet/db content into this sandbox: read the ~130-byte
    pointer, not the multi-MB file it stands in for.

    Scope, stated plainly: this catches whole-file duplicates (same
    dataset checked into two repos, unchanged). It cannot see *inside* a
    parquet or SQLite file, so it will not notice two differently-built
    caches that happen to share 90% of their rows -- that needs the real
    bytes, which this sandbox doesn't have access to for this account's
    LFS storage. *)

val default_extensions : string list
(** [".parquet"; ".db"; ".db.gz"; ".gz"; ".csv"; ".json"; ".xlsx"] -- what
    counts as a "data source" for this catalog. *)

val is_data_file : ?extensions:string list -> Scanner.file_entry -> bool

val parse_lfs_pointer : string -> (string * int) option
(** [parse_lfs_pointer contents] returns [Some (oid, declared_size)] if
    [contents] is a well-formed Git LFS pointer file, [None] otherwise
    (including for a real, non-pointer binary file -- LFS pointers are
    always short, well-formed UTF-8 text, so a real parquet/SQLite file
    fails to parse as one immediately rather than being misread). *)

type cataloged = {
  file : Scanner.file_entry;
  true_size_bytes : int;  (** the pointer's declared size if this is an LFS pointer, else the on-disk size *)
  is_lfs_pointer : bool;
  content_key : string option;  (** ["lfs:" ^ oid], or ["raw:" ^ md5] for a real (non-pointer) file, [None] on read error *)
}

val catalog : ?extensions:string list -> Scanner.file_entry list -> cataloged list
(** Filters to data files by extension, then classifies each one. Every
    call reads the file's own bytes once (cheap for a pointer, which is
    what almost everything LFS-tracked will be in a skip-smudge clone). *)

val duplicates : cataloged list -> Duplicate_finder.group list
(** Groups entries that are LFS pointers (see {!cataloged.is_lfs_pointer})
    by [content_key], reusing {!Duplicate_finder.group_by_key}.
    Deliberately restricted to LFS pointers: a non-pointer data file's
    duplicate, if it has one, is already found by {!Duplicate_finder.find}
    over the general file set (hashing the same bytes either way) -- this
    function only exists to surface the LFS-specific case, not to
    re-report what the general scan already covers. *)

val to_csv_rows : cataloged list -> string list list
(** Header row first, then one row per entry:
    [path; kind; true_size_bytes; is_lfs_pointer; content_key]. *)
