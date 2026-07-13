let is_alnum c = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')
let is_digit c = c >= '0' && c <= '9'

let normalize_stem basename =
  let stem =
    match String.rindex_opt basename '.' with
    | Some i when i > 0 -> String.sub basename 0 i
    | _ -> basename
  in
  let buf = Buffer.create (String.length stem) in
  String.iter
    (fun c ->
      if is_digit c then ()
      else if is_alnum c then Buffer.add_char buf (Char.uppercase_ascii c)
      else Buffer.add_char buf '_')
    stem;
  String.split_on_char '_' (Buffer.contents buf) |> List.filter (fun s -> String.length s > 0)

type cluster = {
  key : string;
  files : Scanner.file_entry list;
}

module StringMap = Map.Make (String)

let cluster ?(min_token_length = 4) (entries : Scanner.file_entry list) : cluster list =
  let by_token =
    List.fold_left
      (fun acc (e : Scanner.file_entry) ->
        let basename = Filename.basename e.rel_path in
        match normalize_stem basename with
        | first :: _ when String.length first >= min_token_length ->
            StringMap.update first (function None -> Some [ e ] | Some xs -> Some (e :: xs)) acc
        | _ -> acc)
      StringMap.empty entries
  in
  let clusters =
    StringMap.fold
      (fun key files acc -> match files with [] | [ _ ] -> acc | _ :: _ :: _ -> { key; files } :: acc)
      by_token []
  in
  List.sort (fun a b -> compare (List.length b.files) (List.length a.files)) clusters
