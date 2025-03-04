#!/usr/bin/env python3
"""
Terraform VPC Security Enhancement Tool

This script automates enhancing AWS VPC configurations with security best practices
by analyzing Terraform code and leveraging Claude to suggest improvements.

The tool performs the following main steps:
1. Clones a Terraform repository and analyzes its structure
2. Builds a dependency graph of Terraform files
3. Identifies relevant files that need security enhancements
4. Generates prompts for Claude AI to add security features
5. Processes the AI responses and saves the enhanced code
"""

import os
import sys
import subprocess
import logging
import argparse
import re
import tiktoken
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Union
import json
import time
from tqdm import tqdm

import hcl2
import networkx as nx
from anthropic import Anthropic

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("terraform-enhancer")

class TerraformEnhancer:
    """
    Main class for enhancing Terraform VPC configurations with security features.
    
    This class handles the entire workflow from repository analysis to code enhancement:
    - Repository cloning and initialization
    - Terraform file dependency analysis
    - Graph visualization
    - Prompt generation for Claude AI
    - Processing AI responses and saving enhanced code
    """
    
    def __init__(
        self, 
        repo_url: str, 
        example_path: str,
        target_dir: str,
        output_dir: str,
        api_key: Optional[str] = None,
        model: str = "claude-3-7-sonnet-20250219",
        debug: bool = True,
        visualize_graph: bool = True,
        update_individually: bool = True
    ):
        """
        Initialize the Terraform enhancer with configuration parameters.
        
        Args:
            repo_url: URL of the Terraform repository to analyze
            example_path: Path to the example directory within the repository
            target_dir: Directory where the repository will be cloned
            output_dir: Directory where enhanced code will be saved
            api_key: Anthropic API key for Claude
            model: Claude model to use for code enhancement
            debug: Enable debug logging
            visualize_graph: Generate a visualization of the dependency graph
            update_individually: Process each file individually (True) or all at once (False)
        """
        # Store configuration parameters
        self.repo_url = repo_url
        self.example_path = example_path
        self.target_dir = Path(target_dir)
        self.output_dir = Path(output_dir)
        self.api_key = api_key
        self.model = model
        self.visualize_graph = visualize_graph
        self.update_individually = update_individually
        
        # Set debug logging if enabled
        if debug:
            logger.setLevel(logging.DEBUG)
            
        # Initialize state variables
        self.example_dir = None  # Path to the example directory
        self.graph = None        # Dependency graph
        self.claude_client = None  # Claude API client
        
        # Initialize token counter for prompt size estimation
        try:
            # Claude uses cl100k tokenizer
            self.encoding = tiktoken.encoding_for_model("cl100k_base")
        except:
            logger.warning("Could not initialize tiktoken, will use character-based approximation")
            self.encoding = None
        
        # Initialize Claude client if API key is provided
        if api_key:
            self.claude_client = Anthropic(api_key=api_key)
    
    def count_tokens(self, text: str) -> int:
        """
        Count the number of tokens in a string for Claude API usage estimation.
        
        Args:
            text: The text to count tokens for
            
        Returns:
            Number of tokens in the text
        """
        if self.encoding:
            # Use tiktoken for accurate token counting
            return len(self.encoding.encode(text))
        else:
            # Approximate token count based on character count (1 token ≈ 4 chars)
            return len(text) // 4
    
    def check_dependencies(self) -> None:
        """
        Verify required external tools (git, terraform) are installed.
        
        Raises:
            RuntimeError: If a required dependency is not found
        """
        for dep in ["git", "terraform"]:
            try:
                subprocess.run(
                    [dep, "--version"], 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE, 
                    check=True
                )
                logger.debug(f"Dependency check passed: {dep}")
            except (subprocess.SubprocessError, FileNotFoundError):
                raise RuntimeError(f"Required dependency '{dep}' not found. Please install it.")
    
    def clone_repository(self) -> Path:
        """
        Clone the target repository and locate the example directory.
        
        Returns:
            Path to the example directory
            
        Raises:
            RuntimeError: If repository cloning fails
            FileNotFoundError: If example path is not found
        """
        # Clone repository if it doesn't exist locally
        if not self.target_dir.exists():
            logger.info(f"Cloning repository from {self.repo_url} to {self.target_dir}")
            try:
                subprocess.run(
                    ["git", "clone", "--depth=1", self.repo_url, str(self.target_dir)], 
                    check=True,
                    capture_output=True
                )
            except subprocess.SubprocessError as e:
                raise RuntimeError(f"Failed to clone repository: {e}")
        else:
            logger.info(f"Repository directory {self.target_dir} already exists, skipping clone")
        
        # Locate example directory within the cloned repository
        example_dir = self.target_dir / self.example_path
        
        if not example_dir.exists():
            raise FileNotFoundError(f"Example path '{example_dir}' not found in repository")
        
        self.example_dir = example_dir
        return example_dir
    
    def init_terraform(self) -> None:
        """
        Initialize Terraform in the example directory.
        
        This runs 'terraform init' to download providers and modules.
        
        Raises:
            RuntimeError: If terraform initialization fails
        """
        logger.info(f"Initializing Terraform in {self.example_dir}")
        try:
            subprocess.run(
                ["terraform", "init"],
                cwd=self.example_dir,
                check=True,
                capture_output=True
            )
        except subprocess.SubprocessError as e:
            logger.error(f"Terraform init failed: {e.stderr.decode() if hasattr(e, 'stderr') else e}")
            raise RuntimeError("Failed to initialize Terraform")
    
    def build_dependency_graph(self) -> nx.DiGraph:
        """
        Build a dependency graph of Terraform files in the repository.
        
        This analyzes module references between files to create a directed graph
        where edges represent dependencies between Terraform files.
        
        Returns:
            NetworkX DiGraph object representing the dependency graph
        """
        repo_root = self.target_dir
        logger.info(f"Building dependency graph from {repo_root}")
        
        # Create an empty directed graph
        graph = nx.DiGraph()
        
        # Find all .tf files in the repository
        tf_files = list(repo_root.glob("**/*.tf"))
        for tf_file in tqdm(tf_files, desc="Scanning Terraform files"):
            # Skip .terraform directories and hidden paths
            if ".terraform" in str(tf_file) or any(p.startswith('.') for p in tf_file.parts):
                continue
                
            file_path = str(tf_file)
            graph.add_node(file_path)
            
            try:
                # Parse the Terraform file to find module references
                with open(tf_file, "r", encoding="utf-8") as f:
                    try:
                        data = hcl2.load(f)
                        
                        # Process module dependencies
                        modules = data.get("module", {})
                        
                        # Handle two different formats hcl2 might return
                        if isinstance(modules, list) and modules:
                            # Format: list of dictionaries
                            self._process_module_list(graph, modules, tf_file, file_path)
                        else:
                            # Format: dictionary format
                            self._process_module_dict(graph, modules, tf_file, file_path)
                            
                    except Exception as e:
                        logger.debug(f"Error parsing HCL in {tf_file}: {e}")
            except Exception as e:
                logger.debug(f"Error reading file {tf_file}: {e}")
        
        logger.info(f"Built graph with {len(graph.nodes)} nodes and {len(graph.edges)} edges")
        self.graph = graph
        
        # Print debug info if no dependencies were found
        if len(graph.edges) == 0:
            self._debug_empty_graph(repo_root)
        
        return graph
    
    def _process_module_list(self, graph, modules, tf_file, file_path):
        """
        Process module references when HCL parser returns a list format.
        
        Args:
            graph: The dependency graph to update
            modules: List of module dictionaries
            tf_file: The current Terraform file
            file_path: String path to the current file
        """
        for module_dict in modules:
            for module_name, module_config in module_dict.items():
                if "source" in module_config:
                    source = module_config["source"]
                    self._add_module_dependency(graph, source, tf_file, file_path)
    
    def _process_module_dict(self, graph, modules, tf_file, file_path):
        """
        Process module references when HCL parser returns a dictionary format.
        
        Args:
            graph: The dependency graph to update
            modules: Dictionary of modules
            tf_file: The current Terraform file
            file_path: String path to the current file
        """
        for module_name, module_config in modules.items():
            if isinstance(module_config, list) and module_config:
                module_config = module_config[0]
            
            source = module_config.get("source", "")
            self._add_module_dependency(graph, source, tf_file, file_path)
    
    def _add_module_dependency(self, graph, source, tf_file, file_path):
        """
        Add module dependency edges to the graph based on a module source.
        
        Args:
            graph: The dependency graph to update
            source: Module source path
            tf_file: The current Terraform file
            file_path: String path to the current file
        """
        # Handle relative module paths including ../ syntax
        if source.startswith(".") or not (source.startswith("git::") or ":" in source):
            # Resolve the relative path against the file directory
            base_dir = tf_file.parent
            try:
                # Handle ../../ type paths properly
                module_path = (base_dir / source).resolve()
                
                # If it points to a directory, find all .tf files
                if module_path.exists() and module_path.is_dir():
                    for module_tf in module_path.glob("*.tf"):
                        graph.add_edge(file_path, str(module_tf))
                        logger.debug(f"Added edge: {file_path} -> {module_tf}")
                # If it points directly to a parent directory
                elif source == "../../" or source == "../":
                    # Handle the special case of pointing to repo root
                    root_path = module_path
                    for root_tf in root_path.glob("*.tf"):
                        graph.add_edge(file_path, str(root_tf))
                        logger.debug(f"Added edge: {file_path} -> {root_tf}")
            except Exception as e:
                logger.debug(f"Error resolving module path for {source}: {e}")
    
    def _debug_empty_graph(self, repo_root):
        """
        Print debug information when no dependencies are found in the graph.
        
        Args:
            repo_root: Root directory of the repository
        """
        logger.warning("No dependencies found in the graph - this is likely an issue")
        # Print some sample module declarations from the files to help debug
        for tf_file in repo_root.glob("**/*.tf"):
            if "example" in str(tf_file):
                try:
                    with open(tf_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        module_matches = re.findall(r'module\s+"[^"]+"\s+{[^}]*source\s+=\s+"[^"]+"', content)
                        if module_matches:
                            logger.debug(f"Found module declarations in {tf_file}:")
                            for match in module_matches:
                                logger.debug(f"  {match}")
                except Exception:
                    pass

    def visualize_dependency_graph(self, entry_point: str, relevant_files: Set[str], output_file: str = "dependency_graph.png"):
        """
        Visualize the dependency graph, highlighting the entry point and relevant files.
        
        Creates a visual representation of the file dependencies to help understand
        the project structure and relationships between Terraform files.
        
        Args:
            entry_point: Path to the main entry point file
            relevant_files: Set of files that are relevant to the entry point
            output_file: Path where the visualization will be saved
        """
        if not self.graph:
            logger.warning("No graph to visualize")
            return
            
        logger.info("Generating graph visualization")
        
        plt.figure(figsize=(14, 10))
        
        # Create a subgraph with only the relevant files for better visualization
        relevant_nodes = {entry_point} | relevant_files
        subgraph = self.graph.subgraph(relevant_nodes)
        
        # Set up node colors to distinguish different types of files
        node_colors = []
        for node in subgraph.nodes():
            if node == entry_point:
                node_colors.append('red')  # Entry point
            elif node in relevant_files:
                node_colors.append('lightblue')  # Relevant files
            else:
                node_colors.append('gray')  # Other files
        
        # Use basenames for node labels to improve readability
        node_labels = {node: os.path.basename(node) for node in subgraph.nodes()}
        
        # Use spring layout for better spacing
        pos = nx.spring_layout(subgraph, seed=42)
        
        # Draw the graph
        nx.draw_networkx(
            subgraph, 
            pos=pos,
            with_labels=True,
            labels=node_labels,
            node_color=node_colors,
            node_size=1000,
            font_size=8,
            arrows=True
        )
        
        # Add a legend to explain the color coding
        legend_elements = [
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='red', markersize=10, label='Entry Point'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='lightblue', markersize=10, label='Relevant Files')
        ]
        plt.legend(handles=legend_elements)
        
        # Add title and other information
        plt.title(f"Terraform Dependency Graph\nEntry: {os.path.basename(entry_point)}, {len(relevant_files)} relevant files")
        plt.axis('off')
        
        # Save the graph to a file
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        logger.info(f"Dependency graph visualization saved to {output_file}")
        
        # Close the plot to free memory
        plt.close()
    
    def get_relevant_files(self, entry_point: Union[str, Path]) -> Set[str]:
        """
        Get all files that the entry point depends on directly or indirectly.
        
        Uses the dependency graph to find all files that are referenced
        from the entry point through module dependencies.
        
        Args:
            entry_point: Path to the main entry point file
            
        Returns:
            Set of paths to files that are relevant to the entry point
            
        Raises:
            ValueError: If dependency graph has not been built
        """
        entry_str = str(entry_point)
        if not self.graph:
            raise ValueError("Dependency graph not built. Call build_dependency_graph first.")
            
        if entry_str not in self.graph:
            logger.warning(f"Entry point {entry_str} not found in dependency graph")
            return set()
        
        try:
            # Get all nodes that can be reached from the entry point
            descendants = nx.descendants(self.graph, entry_str)
            logger.info(f"Found {len(descendants)} files relevant to {entry_point}")
            return set(descendants)
        except nx.NetworkXError as e:
            logger.error(f"Error determining dependent files: {e}")
            return set()
    
    def generate_prompt_for_file(self, target_file: Union[str, Path], context_files: Set[str]) -> Tuple[str, int, int]:
        """
        Generate a prompt for enhancing a specific file with relevant context.
        
        Used in individual file processing mode to create focused prompts
        for each .tf file that needs security enhancements.
        
        Args:
            target_file: Path to the file to enhance
            context_files: Set of files to include as context
            
        Returns:
            Tuple of (prompt, token_count, files_included)
        """
        logger.info(f"Generating prompt for file: {target_file}")
        code_context = []
        files_included = 0
        
        # First add the target file
        try:
            with open(target_file, 'r', encoding="utf-8") as f:
                content = f.read()
                if content.strip():
                    code_context.append(f"FILE: {target_file}\n{content}\n")
                    files_included += 1
        except Exception as e:
            logger.warning(f"Could not read target file {target_file}: {e}")
            return "", 0, 0
        
        # Then add relevant context files
        for file_path in context_files:
            path = Path(file_path)
            if not path.is_file():
                continue
                
            try:
                with open(path, 'r', encoding="utf-8") as f:
                    content = f.read()
                    if content.strip():  # Only include non-empty files
                        code_context.append(f"FILE: {path}\n{content}\n")
                        files_included += 1
            except Exception as e:
                logger.warning(f"Could not read context file {path}: {e}")
        
        # Combine the context
        combined_context = '\n'.join(code_context)
        
        # Create the prompt with security enhancement instructions
        prompt = f"""
You are a Terraform expert. Update the following Terraform file to add security configurations:
{os.path.basename(target_file)}

Add the following security features as appropriate for this specific file:
1. Network ACLs with strict inbound/outbound rules
2. Flow logs for VPC traffic monitoring to CloudWatch
3. Security Group enhancements with least privilege access
4. Encryption for S3 endpoints and any other relevant services
5. VPC Endpoint policies with proper restrictions

IMPORTANT: Format your response as follows:
- Start with "FILE: {os.path.basename(target_file)}"
- Then provide the complete file content with your security enhancements
- DO NOT include markdown code block markers
- DO NOT include any explanatory text outside the actual code
- Include ALL necessary code for the file, not just the changes
- The content must be valid Terraform syntax

Only modify AWS resources, keeping the existing structure and module usage patterns.

Current code context:
{combined_context}
"""
        
        token_count = self.count_tokens(prompt)
        logger.info(f"Generated prompt with {token_count} tokens including {files_included} files")
        return prompt, token_count, files_included
    
    def generate_prompt(self, entry_point: Union[str, Path], relevant_files: Set[str]) -> Tuple[str, int, int]:
        """
        Generate a prompt for enhancing all relevant Terraform files.
        
        Used in batch processing mode to create a single prompt that includes
        all files that need security enhancements.
        
        Args:
            entry_point: Path to the main entry point file
            relevant_files: Set of files that are relevant to the entry point
            
        Returns:
            Tuple of (prompt, token_count, files_included)
        """
        logger.info("Generating prompt with code context")
        code_context = []
        files_to_read = [str(entry_point)] + list(relevant_files)
        files_included = 0
        
        # Collect content from all files
        for file_path in files_to_read:
            path = Path(file_path)
            if not path.is_file():
                continue
                
            try:
                with open(path, 'r', encoding="utf-8") as f:
                    content = f.read()
                    if content.strip():  # Only include non-empty files
                        code_context.append(f"FILE: {path}\n{content}\n")
                        files_included += 1
            except Exception as e:
                logger.warning(f"Could not read file {path}: {e}")
        
        # Handle token limits for large codebases
        combined_context = '\n'.join(code_context)
        token_estimate = self.count_tokens(combined_context)
        
        # If context exceeds token limit, prioritize files to include
        if token_estimate > 80000:  # Leave room for the prompt instructions
            combined_context = self._truncate_context(files_to_read, entry_point)
            files_included = len(combined_context.split("FILE:")) - 1
        
        # Create the prompt with security enhancement instructions
        prompt = f"""
You are a Terraform expert. Update the VPC configuration in {entry_point} 
to add security configurations including:
1. Network ACLs with strict inbound/outbound rules
2. Flow logs for VPC traffic monitoring to CloudWatch
3. Security Group enhancements with least privilege access
4. Encryption for S3 endpoints and any other relevant services
5. VPC Endpoint policies with proper restrictions

IMPORTANT: Format your response as follows:
- For each file you modify, include the filename preceded by "FILE: "
- Example: "FILE: main.tf"
- Then provide the complete file content with your security enhancements
- DO NOT include markdown code block markers
- DO NOT include any explanatory text outside the actual code
- Include ALL necessary code for each file, not just the changes
- The content must be valid Terraform syntax that can be directly saved to .tf files

Only modify AWS resources, keeping the existing structure and module usage patterns.

Current code context:
{combined_context}
"""
        
        total_tokens = self.count_tokens(prompt)
        logger.info(f"Generated prompt with {total_tokens} tokens including {files_included} files")
        return prompt, total_tokens, files_included
    
    def _truncate_context(self, files_to_read, entry_point):
        """
        Truncate context to fit within token limits by prioritizing important files.
        
        Args:
            files_to_read: List of files to consider
            entry_point: Path to the main entry point file
            
        Returns:
            Truncated context string
        """
        logger.warning(f"Context is very large, truncating...")
        truncated_context = []
        priority_files = [str(entry_point)]  # Start with entry point
        other_files = [f for f in files_to_read if f != str(entry_point)]
        
        # Track tokens and files included
        current_tokens = 0
        files_included = 0
        
        # First add priority files
        for file_path in priority_files:
            path = Path(file_path)
            if not path.is_file():
                continue
            
            try:
                with open(path, 'r', encoding="utf-8") as f:
                    content = f.read()
                    if content.strip():
                        file_text = f"FILE: {path}\n{content}\n"
                        file_tokens = self.count_tokens(file_text)
                        
                        if current_tokens + file_tokens <= 70000:  # Conservative limit
                            truncated_context.append(file_text)
                            current_tokens += file_tokens
                            files_included += 1
                        else:
                            logger.warning(f"Skipping priority file {path} due to token limit")
            except Exception as e:
                logger.warning(f"Could not read file {path}: {e}")
        
        # Then add other files until we hit the token limit
        for file_path in other_files:
            path = Path(file_path)
            if not path.is_file():
                continue
            
            try:
                with open(path, 'r', encoding="utf-8") as f:
                    content = f.read()
                    if content.strip():
                        file_text = f"FILE: {path}\n{content}\n"
                        file_tokens = self.count_tokens(file_text)
                        
                        if current_tokens + file_tokens <= 70000:  # Conservative limit
                            truncated_context.append(file_text)
                            current_tokens += file_tokens
                            files_included += 1
                        else:
                            logger.warning(f"Skipping file {path} due to token limit")
            except Exception as e:
                logger.warning(f"Could not read file {path}: {e}")
        
        combined_context = '\n'.join(truncated_context)
        logger.info(f"Truncated context to {self.count_tokens(combined_context)} tokens, {files_included} files")
        return combined_context
    
    def apply_llm_changes(self, prompt: str) -> str:
        """
        Call Claude API and return modified code.
        
        Args:
            prompt: The prompt to send to Claude
            
        Returns:
            Claude's response with enhanced code
            
        Raises:
            ValueError: If Claude client is not initialized
        """
        if not self.claude_client:
            raise ValueError("Claude client not initialized. API key may be missing.")
            
        logger.info(f"Calling Claude API with model: {self.model}")
        
        try:
            # Call Claude API with thinking enabled for better code generation
            message = self.claude_client.messages.create(
                model=self.model,
                stream=False,
                max_tokens=20000,
                temperature=1,  # Higher temperature for more creative enhancements
                messages=[
                    {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }],
                thinking={
                    "type": "enabled",
                    "budget_tokens": 10000  # Allow Claude to think through complex changes
                },
            )

            # Extract text from content list
            content_text = ""
            for content_item in message.content:
                if hasattr(content_item, 'text') and content_item.text:
                    content_text += content_item.text

            logger.debug(f"Received response from Claude")
            return content_text
            
        except Exception as e:
            logger.error(f"Error calling Claude API: {e}")
            raise
    
    def extract_file_content(self, response: str) -> Dict[str, str]:
        """
        Extract file content from Claude's response.
        
        Parses the response to extract each file and its content,
        handling different formats that Claude might use.
        
        Args:
            response: The raw response from Claude
            
        Returns:
            Dictionary mapping filenames to their content
        """
        extracted_files = {}
        
        # Clean the response by removing markdown formatting
        cleaned_response = re.sub(r'```(?:terraform|hcl|tf)?\n', '', response)
        cleaned_response = re.sub(r'```', '', cleaned_response)
        
        # Find file sections using the FILE: header pattern
        file_pattern = re.compile(r'FILE:\s+(.+?\.tf)\s*\n(.*?)(?=FILE:|$)', re.DOTALL)
        file_matches = file_pattern.findall(cleaned_response)
        
        # If no matches with FILE: pattern, try another common pattern
        if not file_matches:
            file_pattern = re.compile(r'(?:^|\n)([^:\n]+\.tf)\s*[:]\s*\n(.*?)(?=\n[^:\n]+\.tf\s*[:]\s*\n|$)', re.DOTALL)
            file_matches = file_pattern.findall(cleaned_response)
        
        # Process each file
        for filename, content in file_matches:
            # Clean up the filename
            clean_filename = filename.strip()
            
            # Clean up the content - remove any leading/trailing whitespace
            clean_content = content.strip()
            
            # Check if content appears to be valid Terraform syntax
            if not re.search(r'(?:provider|module|resource|variable|output|locals)\s+', clean_content):
                logger.warning(f"Content for {clean_filename} doesn't appear to be valid Terraform")
            
            # Handle path components in the filename (extract basename)
            if '/' in clean_filename or '\\' in clean_filename:
                clean_filename = os.path.basename(clean_filename)
                
            extracted_files[clean_filename] = clean_content
            
        # Handle the case where no files could be extracted
        if not extracted_files:
            logger.warning("Could not extract any files from the response")
            # Save the raw response for debugging
            debug_file = self.output_dir / "claude_response.txt"
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(response)
            logger.info(f"Saved raw response to {debug_file} for debugging")
            
        return extracted_files
    
    def save_modified_code(self, file_content_map: Dict[str, str]) -> Dict[str, Path]:
        """
        Save the modified code to output files.
        
        Args:
            file_content_map: Dictionary mapping filenames to their content
            
        Returns:
            Dictionary mapping filenames to their saved file paths
        """
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        saved_files = {}
        
        # Save each file
        for filename, content in file_content_map.items():
            output_file = self.output_dir / filename
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(content)
                
            saved_files[filename] = output_file
            logger.info(f"Saved modified file: {output_file}")
        
        return saved_files
    
    # NOTE: Validation functions are commented out because they cannot work correctly
    # with the current setup where generated files reference modules in their original paths.
    # The validation would fail because:
    # 1. The enhanced files in the output directory reference modules in the original repo
    # 2. These modules are not copied to the output directory
    # 3. Terraform init/validate would fail to locate these modules
    #
    # To enable validation, you would need to:
    # 1. Copy all required modules to the output directory
    # 2. Update module references in the enhanced files to point to the new locations
    # 3. Run terraform init and validate in the output directory
    
    def enhance_individual_files(self, entry_point: Path, all_files: List[Path]) -> Dict[str, Path]:
        """
        Process each file individually with Claude.
        
        This approach processes one file at a time, providing focused context
        for each file. This helps with token limits and gives Claude more
        focused attention on each specific file.
        
        Args:
            entry_point: Path to the main entry point file
            all_files: List of all files to process
            
        Returns:
            Dictionary mapping filenames to their saved paths
        """
        logger.info("Processing files individually")
        all_saved_files = {}
        
        # Start with the entry point to ensure it's processed first
        primary_files = [entry_point]
        
        # Then add other .tf files in the example directory
        secondary_files = [f for f in all_files if f != entry_point]
        
        # Process all files, starting with primary files
        for file in tqdm(primary_files + secondary_files, desc="Processing files"):
            if not file.exists() or not file.is_file():
                logger.warning(f"Skipping non-existent file: {file}")
                continue
                
            logger.info(f"Processing file: {file}")
            
            # Get minimal context - just the file itself and its direct dependencies
            context_files = set()
            if self.graph and str(file) in self.graph:
                direct_deps = set(self.graph.successors(str(file)))
                context_files.update(direct_deps)
            
            # Generate prompt for this specific file
            prompt, token_count, files_included = self.generate_prompt_for_file(file, context_files)
            
            if not prompt:
                logger.warning(f"Could not generate prompt for {file}, skipping")
                continue
                
            # Call Claude API
            try:
                modified_code = self.apply_llm_changes(prompt)
                
                # Extract file content
                file_content_map = self.extract_file_content(modified_code)
                
                if not file_content_map:
                    logger.warning(f"No valid content extracted for {file}, skipping")
                    continue
                
                # Save the modified files
                saved_files = self.save_modified_code(file_content_map)
                all_saved_files.update(saved_files)
                
                logger.info(f"Successfully processed {file}")
                
                # Add a delay between API calls to avoid rate limiting
                logger.info("Sleeping for 30 seconds to avoid rate limiting")
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Error processing {file}: {e}")
        
        return all_saved_files
    
    def run(self, apply_changes: bool = True) -> int:
        """
        Run the complete enhancement process.
        
        This is the main method that orchestrates the entire workflow.
        
        Args:
            apply_changes: Whether to apply changes using Claude or just generate the prompt
            
        Returns:
            Exit code (0 for success, non-zero for errors)
        """
        try:
            # Step 1: Check dependencies
            self.check_dependencies()
            
            # Step 2: Clone repository
            self.clone_repository()
            
            # Step 3: Initialize Terraform
            self.init_terraform()
            
            # Step 4: Build dependency graph
            self.build_dependency_graph()
            
            # Step 5: Identify entry point and relevant files
            entry_point = self.example_dir / "main.tf"
            if not entry_point.exists():
                raise FileNotFoundError(f"Entry point file {entry_point} not found")
            
            relevant_files = self.get_relevant_files(entry_point)
            
            # Step 6: Visualize the dependency graph if requested
            if self.visualize_graph:
                self.visualize_dependency_graph(str(entry_point), relevant_files)
            
            # Step 7: Apply changes using Claude (if requested)
            if apply_changes:
                if not self.api_key:
                    raise ValueError("ANTHROPIC_API_KEY environment variable not set")
                
                # Create the output directory
                self.output_dir.mkdir(parents=True, exist_ok=True)
                
                if self.update_individually:
                    # Step 7a: Process files one by one
                    all_tf_files = list(self.example_dir.glob("*.tf"))
                    logger.info(f"Found {len(all_tf_files)} .tf files in the example directory")
                    logger.info(f'Files found in the example directory: {all_tf_files}')
                    saved_files = self.enhance_individual_files(entry_point, all_tf_files)
                else:
                    # Step 7b: Process all files together in one prompt
                    prompt, token_count, files_count = self.generate_prompt(entry_point, relevant_files)
                    
                    # Print statistics
                    logger.info("=" * 50)
                    logger.info(f"Prompt Statistics:")
                    logger.info(f"- Total tokens: {token_count}")
                    logger.info(f"- Files included: {files_count}")
                    logger.info(f"- Relevant files found: {len(relevant_files)}")
                    logger.info("=" * 50)
                    
                    # Call Claude
                    modified_code = self.apply_llm_changes(prompt)
                    
                    # Extract and save files
                    file_content_map = self.extract_file_content(modified_code)
                    saved_files = self.save_modified_code(file_content_map)
                    
                if not saved_files:
                    logger.error("No valid Terraform files could be extracted from the response")
                    return 1
                
                # Note: We're skipping validation because the enhanced files reference modules
                # in the original repo, which won't be accessible from the output directory.
                # This would cause validation to fail regardless of the quality of the changes.
                logger.info("=" * 50)
                logger.info("Skipping Terraform validation due to external module references.")
                logger.info("The enhanced files reference modules from the original repository,")
                logger.info("which would not be accessible from the output directory.")
                logger.info("=" * 50)
                
                # Show summary of created files
                logger.info("=" * 50)
                logger.info(f"Enhanced code saved to: {self.output_dir}")
                for filename, path in saved_files.items():
                    logger.info(f"  - {filename}")
                logger.info("=" * 50)
                
            else:
                logger.info("Prompt generated but apply_changes=False, stopping here")
            
            return 0
        
        except Exception as e:
            logger.exception(f"Error during enhancement process: {e}")
            return 1

def parse_arguments():
    """
    Parse command line arguments.
    
    Returns:
        Parsed argument object with configuration options
    """
    parser = argparse.ArgumentParser(
        description="Enhance Terraform AWS VPC configurations with security improvements"
    )
    
    parser.add_argument(
        "--repo-url", 
        default="https://github.com/terraform-aws-modules/terraform-aws-vpc.git",
        help="URL of the Terraform repository to enhance"
    )
    
    parser.add_argument(
        "--example-path", 
        default="examples/complete",
        help="Path to the example directory within the repository"
    )
    
    parser.add_argument(
        "--target-dir", 
        default="terraform-aws-vpc",
        help="Directory where the repository will be cloned"
    )
    
    parser.add_argument(
        "--output-dir", 
        default="modified_code",
        help="Directory where modified code will be saved"
    )
    
    parser.add_argument(
        "--claude-model", 
        default="claude-3-7-sonnet-20250219",
        help="Claude model to use for code enhancement"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate prompt but don't apply changes with Claude"
    )
    
    parser.add_argument(
        "--no-graph",
        action="store_true",
        help="Skip generating the dependency graph visualization"
    )
    
    parser.add_argument(
        "--batch-process",
        action="store_true",
        help="Process all files together in one prompt (default is individual files)"
    )
    
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging"
    )
    
    return parser.parse_args()

def main():
    """
    Main entry point for the script.
    
    Parses arguments, initializes the enhancer, and runs the enhancement process.
    
    Returns:
        Exit code (0 for success, non-zero for errors)
    """
    args = parse_arguments()
    
    # Initialize the enhancer with command line arguments
    enhancer = TerraformEnhancer(
        repo_url=args.repo_url,
        example_path=args.example_path,
        target_dir=args.target_dir,
        output_dir=args.output_dir,
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        model=args.claude_model,
        debug=args.debug,
        visualize_graph=not args.no_graph,
        update_individually=not args.batch_process
    )
    
    # Run the enhancement process
    return enhancer.run(apply_changes=not args.dry_run)

if __name__ == "__main__":
    sys.exit(main())