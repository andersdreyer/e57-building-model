# Run inside SketchUp's Ruby console after setting E57_DAE_INPUT and E57_SKP_OUTPUT.
# Example:
# ENV['E57_DAE_INPUT'] = '/absolute/path/model.dae'
# ENV['E57_SKP_OUTPUT'] = '/absolute/path/model.skp'
# load '/absolute/path/to/e57-building-model/scripts/sketchup_import.rb'

require 'time'

dae_path = ENV['E57_DAE_INPUT'] || '/ABSOLUTE/PATH/model.dae'
skp_path = ENV['E57_SKP_OUTPUT'] || '/ABSOLUTE/PATH/model.skp'

raise "DAE input does not exist: #{dae_path}" unless File.file?(dae_path)

model = Sketchup.active_model
model.start_operation('Import constrained E57 model', true)
begin
  before = model.entities.to_a
  options = { 'merge_coplanar_faces' => true, 'show_summary' => false }
  success = model.import(dae_path, options)
  raise "SketchUp could not import #{dae_path}" unless success

  imported = model.entities.to_a - before
  tag = model.layers['E57 reconstructed model'] || model.layers.add('E57 reconstructed model')
  imported.each { |entity| entity.layer = tag if entity.respond_to?(:layer=) }
  model.set_attribute('E57 Building Model', 'source_dae', File.expand_path(dae_path))
  model.set_attribute('E57 Building Model', 'generated_at_utc', Time.now.utc.iso8601)
  model.commit_operation
rescue StandardError
  model.abort_operation
  raise
end

raise "SketchUp could not save #{skp_path}" unless model.save(skp_path)

puts "Saved SketchUp model: #{skp_path}"
