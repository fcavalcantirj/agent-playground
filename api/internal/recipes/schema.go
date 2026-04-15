package recipes

import (
	"bytes"
	_ "embed"
	"errors"
	"fmt"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"sigs.k8s.io/yaml"
)

// recipeSchemaJSON is the canonical ap.recipe/v1 JSON Schema, embedded
// at build time so the Go API carries exactly one schema and no file
// system dependency at startup. The same bytes live on disk at
// agents/schemas/recipe.schema.json; `make copy-schema` keeps the two
// files byte-identical.
//
//go:embed schema/recipe.schema.json
var recipeSchemaJSON []byte

// SchemaValidator compiles the embedded Draft 2019-09 schema once at
// construction time and exposes a single ValidateYAML entry point.
// Callers (the Loader) construct it once at API boot and reuse it for
// every recipe file.
type SchemaValidator struct {
	schema *jsonschema.Schema
}

// NewSchemaValidator parses and compiles the embedded recipe schema
// using Draft 2019-09 semantics. Any parse/compile failure is returned
// as an error — the API must refuse to boot if the schema cannot be
// loaded, because every downstream recipe would be unchecked.
func NewSchemaValidator() (*SchemaValidator, error) {
	doc, err := jsonschema.UnmarshalJSON(bytes.NewReader(recipeSchemaJSON))
	if err != nil {
		return nil, fmt.Errorf("recipes: parse schema: %w", err)
	}
	c := jsonschema.NewCompiler()
	c.DefaultDraft(jsonschema.Draft2019)
	if err := c.AddResource("recipe.schema.json", doc); err != nil {
		return nil, fmt.Errorf("recipes: add schema resource: %w", err)
	}
	sch, err := c.Compile("recipe.schema.json")
	if err != nil {
		return nil, fmt.Errorf("recipes: compile schema: %w", err)
	}
	return &SchemaValidator{schema: sch}, nil
}

// ValidateYAML validates a raw YAML recipe against the compiled schema.
// YAML is first converted to JSON via sigs.k8s.io/yaml.YAMLToJSONStrict
// (which rejects duplicate keys — first DoS guard per threat model
// T-02.5-06) and then parsed via jsonschema.UnmarshalJSON before being
// handed to the compiled validator.
//
// On failure the returned error wraps the jsonschema detailed-output
// diagnostic so the caller gets a JSON pointer to the offending path.
func (v *SchemaValidator) ValidateYAML(raw []byte) error {
	jsonBytes, err := yaml.YAMLToJSONStrict(raw)
	if err != nil {
		return fmt.Errorf("recipes: yaml→json: %w", err)
	}
	inst, err := jsonschema.UnmarshalJSON(bytes.NewReader(jsonBytes))
	if err != nil {
		return fmt.Errorf("recipes: unmarshal json: %w", err)
	}
	if err := v.schema.Validate(inst); err != nil {
		var ve *jsonschema.ValidationError
		if errors.As(err, &ve) {
			return fmt.Errorf("recipes: schema validation: %+v", ve.DetailedOutput())
		}
		return fmt.Errorf("recipes: schema validation: %w", err)
	}
	return nil
}
