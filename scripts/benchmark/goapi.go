// goapi prints, as JSON, what interface.py needs of Go source (standard
// library only; go run goapi.go <mode> <file>...):
//
//	decls <file>...  the top-level declarations of the files, each without a
//	                 body: functions and methods, types (a struct's and an
//	                 interface's members one by one as well), variables and
//	                 constants
//	uses <file>...   the names the files use: identifiers, selected names and
//	                 composite-literal keys, the names they declare, the
//	                 paths they import and the types they make empty (T{})
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/printer"
	"go/token"
	"os"
	"strings"
)

type decl struct {
	Key     string `json:"key"`     // name, Recv.name, or Type.member
	Kind    string `json:"kind"`    // func, method, type, field, embedded, var, const
	Name    string `json:"name"`    // what a use names
	Text    string `json:"text"`    // the declaration as written, without a body
	Package string `json:"package"` // the package clause
}

type uses struct {
	Idents   []string `json:"idents"`   // bare identifiers
	Selected []string `json:"selected"` // x.Name and Key: in a composite literal
	Declared []string `json:"declared"` // top-level names the files declare
	Imports  []string `json:"imports"`  // the import paths
	Zero     []string `json:"zero"`     // types made as T{}: their zero value is used
	Package  string   `json:"package"`
}

func main() {
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, "usage: go run goapi.go decls|uses <file>...")
		os.Exit(2)
	}
	fset := token.NewFileSet()
	var files []*ast.File
	for _, p := range os.Args[2:] {
		f, err := parser.ParseFile(fset, p, nil, parser.SkipObjectResolution)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		files = append(files, f)
	}
	var out any
	switch os.Args[1] {
	case "decls":
		out = decls(fset, files)
	case "uses":
		out = used(files)
	default:
		os.Exit(2)
	}
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		os.Exit(1)
	}
}

func text(fset *token.FileSet, node any) string {
	var b bytes.Buffer
	cfg := printer.Config{Mode: printer.UseSpaces | printer.TabIndent, Tabwidth: 8}
	if err := cfg.Fprint(&b, fset, node); err != nil {
		return ""
	}
	return b.String()
}

func recvName(e ast.Expr) string {
	switch t := e.(type) {
	case *ast.StarExpr:
		return recvName(t.X)
	case *ast.IndexExpr:
		return recvName(t.X)
	case *ast.IndexListExpr:
		return recvName(t.X)
	case *ast.Ident:
		return t.Name
	case *ast.SelectorExpr: // an embedded sync.Mutex is the field Mutex
		return t.Sel.Name
	}
	return ""
}

func decls(fset *token.FileSet, files []*ast.File) []decl {
	out := []decl{}
	for _, f := range files {
		pkg := f.Name.Name
		for _, d := range f.Decls {
			switch d := d.(type) {
			case *ast.FuncDecl:
				fn := *d
				fn.Body, fn.Doc = nil, nil
				k := decl{Key: d.Name.Name, Kind: "func", Name: d.Name.Name, Text: text(fset, &fn), Package: pkg}
				if d.Recv != nil && len(d.Recv.List) > 0 {
					k.Kind, k.Key = "method", recvName(d.Recv.List[0].Type)+"."+d.Name.Name
				}
				out = append(out, k)
			case *ast.GenDecl:
				for _, s := range d.Specs {
					switch s := s.(type) {
					case *ast.TypeSpec:
						out = append(out, decl{Key: s.Name.Name, Kind: "type", Name: s.Name.Name,
							Text: "type " + text(fset, s), Package: pkg})
						var fields *ast.FieldList
						iface := false
						switch t := s.Type.(type) {
						case *ast.StructType:
							fields = t.Fields
						case *ast.InterfaceType:
							fields, iface = t.Methods, true
						}
						if fields == nil {
							continue
						}
						for _, fl := range fields.List {
							line := strings.TrimSpace(text(fset, fl.Type))
							for _, n := range fl.Names {
								member := n.Name + " " + line
								if _, ok := fl.Type.(*ast.FuncType); ok && iface { // F() int, not F func() int
									member = n.Name + strings.TrimPrefix(line, "func")
								}
								out = append(out, decl{Key: s.Name.Name + "." + n.Name, Kind: "field", Name: n.Name,
									Text: member, Package: pkg})
							}
							if len(fl.Names) == 0 { // embedded: its promoted members are the tests' too
								n := recvName(fl.Type)
								out = append(out, decl{Key: s.Name.Name + "." + n, Kind: "embedded", Name: n, Text: line, Package: pkg})
							}
						}
					case *ast.ValueSpec:
						kind := strings.ToLower(d.Tok.String())
						for i, n := range s.Names {
							// the name and its type, never its value: a function
							// value shows its signature (review 292 B2)
							t := kind + " " + n.Name
							if s.Type != nil {
								t += " " + text(fset, s.Type)
							} else if i < len(s.Values) {
								if fn, ok := s.Values[i].(*ast.FuncLit); ok {
									t += " " + text(fset, fn.Type)
								} else {
									t += " = …"
								}
							}
							out = append(out, decl{Key: n.Name, Kind: kind, Name: n.Name, Text: t, Package: pkg})
						}
					}
				}
			}
		}
	}
	return out
}

func used(files []*ast.File) uses {
	idents, selected, declared, imports, zero := map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]bool{}, map[string]bool{}
	u := uses{}
	for _, f := range files {
		u.Package = f.Name.Name
		for _, im := range f.Imports {
			imports[strings.Trim(im.Path.Value, "`\"")] = true
		}
		sel := map[*ast.Ident]bool{}
		ast.Inspect(f, func(n ast.Node) bool {
			switch n := n.(type) {
			case *ast.SelectorExpr:
				sel[n.Sel] = true
				selected[n.Sel.Name] = true
			case *ast.CompositeLit:
				if n.Type != nil && len(n.Elts) == 0 {
					zero[recvName(n.Type)] = true
					if se, ok := n.Type.(*ast.SelectorExpr); ok {
						zero[se.Sel.Name] = true
					}
				}
			case *ast.KeyValueExpr:
				if id, ok := n.Key.(*ast.Ident); ok {
					sel[id] = true
					selected[id.Name] = true
				}
			case *ast.Ident:
				if !sel[n] {
					idents[n.Name] = true
				}
			}
			return true
		})
		for _, d := range f.Decls {
			switch d := d.(type) {
			case *ast.FuncDecl:
				if d.Recv == nil {
					declared[d.Name.Name] = true
				}
			case *ast.GenDecl:
				for _, s := range d.Specs {
					switch s := s.(type) {
					case *ast.TypeSpec:
						declared[s.Name.Name] = true
					case *ast.ValueSpec:
						for _, n := range s.Names {
							declared[n.Name] = true
						}
					}
				}
			}
		}
	}
	for k := range idents {
		u.Idents = append(u.Idents, k)
	}
	for k := range selected {
		u.Selected = append(u.Selected, k)
	}
	for k := range declared {
		u.Declared = append(u.Declared, k)
	}
	for k := range imports {
		u.Imports = append(u.Imports, k)
	}
	for k := range zero {
		if k != "" {
			u.Zero = append(u.Zero, k)
		}
	}
	return u
}
