import json
import os
import math
import random
from typing import Dict, List, Any, Tuple

RL_STATE_FILE = "rl_state.json"
ACTIONS = ["Direct", "Web Search", "RAG Document Search", "Hybrid"]

class RLAgent:
    def __init__(self, alpha: float = 0.2, gamma: float = 0.9, epsilon: float = 0.15, temperature: float = 0.5):
        self.alpha = alpha  # Learning rate
        self.gamma = gamma  # Discount factor
        self.epsilon = epsilon  # Exploration rate
        self.temperature = temperature # Softmax temperature
        
        self.q_table: Dict[str, Dict[str, float]] = {}
        self.action_counts: Dict[str, int] = {a: 0 for a in ACTIONS}
        self.reward_history: List[Dict[str, Any]] = []
        self.total_reward: float = 0.0
        self.total_interactions: int = 0
        
        self.load_state()

    def extract_state(self, query: str, has_docs: bool = False, force_tools: List[str] = None) -> str:
        q_lower = query.lower()
        
        # Keyword detection
        search_keywords = ["search", "latest", "news", "today", "weather", "who is", "what is", "price", "current", "update", "when did", "http", "www"]
        doc_keywords = ["document", "file", "pdf", "text", "uploaded", "summary", "report", "policy", "clause", "contract", "data"]
        
        is_search = any(k in q_lower for k in search_keywords)
        is_doc = any(k in q_lower for k in doc_keywords) or has_docs
        
        length_cat = "short" if len(query) < 30 else ("medium" if len(query) < 100 else "long")
        
        state_key = f"search={is_search}|doc={is_doc}|len={length_cat}"
        return state_key

    def _init_state_if_needed(self, state: str):
        if state not in self.q_table:
            self.q_table[state] = {a: 0.0 for a in ACTIONS}

    def select_action(self, state: str, manual_override: str = None) -> Tuple[str, float, bool]:
        """
        Selects an action based on context state and current Q-table policy.
        Returns: (selected_action, expected_reward, is_exploration)
        """
        if manual_override and manual_override in ACTIONS:
            return manual_override, self.q_table.get(state, {}).get(manual_override, 0.0), False

        self._init_state_if_needed(state)
        q_vals = self.q_table[state]
        
        # Epsilon-greedy exploration
        if random.random() < self.epsilon:
            action = random.choice(ACTIONS)
            is_exploration = True
        else:
            # Exploitation - choose action with highest Q-value
            max_q = max(q_vals.values())
            best_actions = [a for a, q in q_vals.items() if q == max_q]
            action = random.choice(best_actions)
            is_exploration = False
            
        self.action_counts[action] += 1
        self.total_interactions += 1
        return action, q_vals[action], is_exploration

    def update_reward(self, state: str, action: str, reward: float):
        """
        Updates Q-value based on user feedback reward signal (-1.0 or +1.0).
        """
        self._init_state_if_needed(state)
        old_q = self.q_table[state][action]
        
        # Q-learning / Contextual Bandit update rule
        new_q = old_q + self.alpha * (reward - old_q)
        self.q_table[state][action] = round(new_q, 4)
        
        self.total_reward += reward
        self.reward_history.append({
            "interaction": self.total_interactions,
            "state": state,
            "action": action,
            "reward": reward,
            "old_q": round(old_q, 4),
            "new_q": round(new_q, 4)
        })
        
        # Save updated state
        self.save_state()

    def get_policy_distribution(self, state: str) -> Dict[str, float]:
        """
        Computes Softmax probabilities over actions for a given state.
        """
        self._init_state_if_needed(state)
        q_vals = self.q_table[state]
        
        exp_q = {a: math.exp(v / self.temperature) for a, v in q_vals.items()}
        sum_exp = sum(exp_q.values()) or 1.0
        
        return {a: round(exp_q[a] / sum_exp, 3) for a in ACTIONS}

    def get_statistics(self) -> Dict[str, Any]:
        """
        Returns stats for the RL analytics dashboard.
        """
        avg_reward = (self.total_reward / max(1, len(self.reward_history))) if self.reward_history else 0.0
        
        # Compute overall state Q-table overview
        overall_q = {a: 0.0 for a in ACTIONS}
        if self.q_table:
            for st, q_vals in self.q_table.items():
                for a, q in q_vals.items():
                    overall_q[a] += q
            for a in ACTIONS:
                overall_q[a] = round(overall_q[a] / len(self.q_table), 3)

        return {
            "total_interactions": self.total_interactions,
            "total_reward": round(self.total_reward, 2),
            "average_reward": round(avg_reward, 3),
            "action_counts": self.action_counts,
            "overall_q_values": overall_q,
            "q_table": self.q_table,
            "reward_history": self.reward_history[-20:], # Last 20 interactions
            "epsilon": self.epsilon,
            "alpha": self.alpha
        }

    def save_state(self):
        try:
            data = {
                "q_table": self.q_table,
                "action_counts": self.action_counts,
                "reward_history": self.reward_history,
                "total_reward": self.total_reward,
                "total_interactions": self.total_interactions
            }
            with open(RL_STATE_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving RL state: {e}")

    def load_state(self):
        if os.path.exists(RL_STATE_FILE):
            try:
                with open(RL_STATE_FILE, "r") as f:
                    data = json.load(f)
                    self.q_table = data.get("q_table", {})
                    self.action_counts = data.get("action_counts", {a: 0 for a in ACTIONS})
                    self.reward_history = data.get("reward_history", [])
                    self.total_reward = data.get("total_reward", 0.0)
                    self.total_interactions = data.get("total_interactions", 0)
            except Exception as e:
                print(f"Error loading RL state: {e}")

# Global RL agent instance
rl_agent = RLAgent()
