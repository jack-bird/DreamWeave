"""Lore file system for managing world knowledge and narrative elements."""

import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
import re


class LoreSystem:
    """Manages world lore files and provides retrieval functionality."""
    
    def __init__(self, worlds_path: str = None):
        """Initialize the lore system.
        
        Args:
            worlds_path: Path to the worlds directory containing lore files
        """
        if worlds_path is None:
            # Default path relative to this file
            current_dir = Path(__file__).parent
            project_root = current_dir.parent.parent.parent.parent
            worlds_path = project_root / "packages" / "worlds"
        
        self.worlds_path = Path(worlds_path)
        self.current_world = "default_world"
        self._lore_cache = {}
        self._character_cache = None
        self._style_cache = None
        self._rules_cache = None
        self._locations_cache = None
        self._factions_cache = None
    
    def get_world_path(self, world_name: str = None) -> Path:
        """Get the path to a specific world directory."""
        world = world_name or self.current_world
        return self.worlds_path / world
    
    def load_lore(self, world_name: str = None) -> str:
        """Load the main lore file for a world."""
        world = world_name or self.current_world
        if world in self._lore_cache:
            return self._lore_cache[world]
        
        lore_path = self.get_world_path(world) / "lore.md"
        if not lore_path.exists():
            return f"# {world.title()} World\n\nNo detailed lore available yet."
        
        with open(lore_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self._lore_cache[world] = content
            return content
    
    def load_characters(self, world_name: str = None) -> Dict[str, Any]:
        """Load character definitions for a world."""
        world = world_name or self.current_world
        if self._character_cache is not None:
            return self._character_cache
        
        characters_path = self.get_world_path(world) / "characters.json"
        if not characters_path.exists():
            return {}
        
        with open(characters_path, 'r', encoding='utf-8') as f:
            self._character_cache = json.load(f)
            return self._character_cache
    
    def load_style(self, world_name: str = None) -> str:
        """Load the style guide for a world."""
        world = world_name or self.current_world
        if self._style_cache is not None:
            return self._style_cache
        
        style_path = self.get_world_path(world) / "style.md"
        if not style_path.exists():
            return "Use second-person perspective ('你'), create immersive descriptions, and maintain atmospheric storytelling."
        
        with open(style_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self._style_cache = content
            return content
    
    def load_rules(self, world_name: str = None) -> str:
        """Load the rules and constraints for a world."""
        world = world_name or self.current_world
        if self._rules_cache is not None:
            return self._rules_cache
        
        rules_path = self.get_world_path(world) / "rules.md"
        if not rules_path.exists():
            return "Maintain world consistency, respect player agency, and avoid making decisions for the player."
        
        with open(rules_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self._rules_cache = content
            return content
    
    def load_locations(self, world_name: str = None) -> str:
        """Load location descriptions for a world."""
        world = world_name or self.current_world
        if self._locations_cache is not None:
            return self._locations_cache
        
        locations_path = self.get_world_path(world) / "locations.md"
        if not locations_path.exists():
            return "# Locations\n\nVarious locations in the world await exploration."
        
        with open(locations_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self._locations_cache = content
            return content
    
    def load_factions(self, world_name: str = None) -> str:
        """Load faction information for a world."""
        world = world_name or self.current_world
        if self._factions_cache is not None:
            return self._factions_cache
        
        factions_path = self.get_world_path(world) / "factions.md"
        if not factions_path.exists():
            return "# Factions\n\nVarious groups and organizations influence the world."
        
        with open(factions_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self._factions_cache = content
            return content
    
    def retrieve_relevant_lore(self, 
                              user_input: str, 
                              current_scene: str = "",
                              active_characters: List[str] = None,
                              world_name: str = None,
                              max_sections: int = 5) -> List[str]:
        """Retrieve lore sections relevant to the current context.
        
        Args:
            user_input: The user's current input/action
            current_scene: The current scene or location
            active_characters: List of active character names
            world_name: The world to search in
            max_sections: Maximum number of sections to return
            
        Returns:
            List of relevant lore sections
        """
        world = world_name or self.current_world
        relevant_sections = []
        
        # Build search terms from context
        search_terms = []
        
        # Extract keywords from user input
        input_words = re.findall(r'[\w]+', user_input.lower())
        search_terms.extend(input_words[:5])  # Take first 5 meaningful words
        
        # Add scene name
        if current_scene:
            search_terms.append(current_scene.lower())
        
        # Add character names
        if active_characters:
            for char in active_characters:
                search_terms.append(char.lower())
        
        # Search through all lore files
        all_lore = {}
        all_lore['main_lore'] = self.load_lore(world)
        all_lore['characters'] = json.dumps(self.load_characters(world), ensure_ascii=False)
        all_lore['locations'] = self.load_locations(world)
        all_lore['factions'] = self.load_factions(world)
        
        # Find relevant sections
        for lore_type, content in all_lore.items():
            sections = self._find_relevant_sections(content, search_terms, max_sections)
            relevant_sections.extend(sections)
            
            if len(relevant_sections) >= max_sections:
                break
        
        return relevant_sections[:max_sections]
    
    def _find_relevant_sections(self, content: str, search_terms: List[str], max_results: int) -> List[str]:
        """Find sections in content that match search terms."""
        relevant_sections = []
        
        # Split by headers and content blocks
        sections = re.split(r'(#{1,3}\s+[^\n]+)', content)
        
        for i in range(1, len(sections), 2):
            if i + 1 < len(sections):
                header = sections[i].strip()
                body = sections[i + 1].strip()
                section_text = f"{header}\n{body}"
                
                # Check relevance
                relevance_score = self._calculate_relevance(section_text, search_terms)
                if relevance_score > 0:
                    relevant_sections.append({
                        'text': section_text,
                        'score': relevance_score
                    })
        
        # Sort by relevance and return top results
        relevant_sections.sort(key=lambda x: x['score'], reverse=True)
        return [section['text'] for section in relevant_sections[:max_results]]
    
    def _calculate_relevance(self, text: str, search_terms: List[str]) -> int:
        """Calculate relevance score of text to search terms."""
        text_lower = text.lower()
        score = 0
        
        for term in search_terms:
            if term in text_lower:
                # Exact match gets higher score
                score += 2
                # Word boundary match gets medium score
                if re.search(r'\b' + re.escape(term) + r'\b', text_lower):
                    score += 1
        
        return score
    
    def get_narrative_prompt(self, world_name: str = None) -> str:
        """Get a complete narrative prompt combining all lore elements."""
        world = world_name or self.current_world
        
        style = self.load_style(world)
        rules = self.load_rules(world)
        
        return f"""STORYTELLING STYLE GUIDE:
{style}

WORLD RULES AND CONSTRAINTS:
{rules}

Remember these guidelines throughout the narrative generation process."""
    
    def clear_cache(self):
        """Clear all cached lore data."""
        self._lore_cache = {}
        self._character_cache = None
        self._style_cache = None
        self._rules_cache = None
        self._locations_cache = None
        self._factions_cache = None


class SimpleLoreRetriever:
    """Simple keyword-based lore retriever for the MVP version."""
    
    def __init__(self, lore_system: LoreSystem):
        self.lore_system = lore_system
    
    def retrieve_context_for_generation(self,
                                       user_input: str,
                                       current_scene: str = "",
                                       story_state: Dict[str, Any] = None,
                                       world_name: str = None) -> str:
        """Retrieve and format context for story generation.
        
        Args:
            user_input: User's current input
            current_scene: Current scene/location
            story_state: Current story state
            world_name: World name
            
        Returns:
            Formatted context string for prompt injection
        """
        world = world_name or self.lore_system.current_world
        
        # Get base lore
        main_lore = self.lore_system.load_lore(world)
        
        # Get relevant lore sections
        active_characters = list(story_state.get('characters', {}).keys()) if story_state else []
        relevant_lore = self.lore_system.retrieve_relevant_lore(
            user_input=user_input,
            current_scene=current_scene,
            active_characters=active_characters,
            world_name=world,
            max_sections=3
        )
        
        # Build context
        context_parts = [
            "=== WORLD SETTING ===",
            main_lore[:1000],  # Limit main lore length
            ""
        ]
        
        if current_scene:
            locations = self.lore_system.load_locations(world)
            context_parts.extend([
                "=== CURRENT LOCATION INFO ===",
                f"Current scene: {current_scene}",
                locations[:800],  # Limit locations length
                ""
            ])
        
        if relevant_lore:
            context_parts.extend([
                "=== RELEVANT LORE ===",
                *relevant_lore,
                ""
            ])
        
        # Get narrative guidelines
        narrative_guide = self.lore_system.get_narrative_prompt(world)
        context_parts.extend([
            "=== NARRATIVE GUIDELINES ===",
            narrative_guide
        ])
        
        return "\n".join(context_parts)