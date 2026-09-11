// cytoscape-dagre ships no bundled types; register it as a Cytoscape extension.
declare module "cytoscape-dagre" {
  import type cytoscape from "cytoscape";
  const ext: cytoscape.Ext;
  export default ext;
}
