"""
LangChain Integration for Orchestrator
═════════════════════════════════════════════════════════════════════════════
Transforms Orchestrator from simple voting coordinator to intelligent decision-maker.

Features:
  ✓ LLM-powered trading decision coordination
  ✓ Explainable reasoning for all trades
  ✓ Dynamic strategy selection based on market conditions
  ✓ Cross-service orchestration via LangChain agents
  ✓ Structured decision output with confidence scores
  ✓ Context-aware execution strategies

Architecture:
  Market Data (Portfolio Service)
    ↓
  LLM Agent (LangChain)
    ├─ Gets market data
    ├─ Runs strategy analysis
    ├─ Checks risk constraints
    ├─ Makes decision + explanation
    ↓
  Execution (Execution Service)
"""

import json
import os
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict
import httpx
import logging

logger = logging.getLogger(__name__)

# Try to import LangChain (may not be installed yet)
try:
    from langchain.agents import AgentExecutor, create_openai_functions_agent
    from langchain.tools import tool, Tool
    from langchain_openai import ChatOpenAI
    from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain.memory import ConversationBufferMemory
    from langchain.schema import HumanMessage, AIMessage, SystemMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logger.warning("LangChain not installed. Install with: pip install langchain langchain-openai")


@dataclass
class TradingDecision:
    """Structured output from LLM trading decision."""
    action: str  # "EXECUTE", "SKIP", "WAIT"
    confidence: float  # 0-1
    reasoning: str
    strategy: str
    pair: str
    side: Optional[str]  # "BUY" or "SELL"
    quantity: Optional[float]
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    alternative_strategies: list
    market_condition: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TradingTools:
    """Tools available to LLM agent for trading decisions."""
    
    def __init__(self, base_url: str = "http://localhost"):
        self.base_url = base_url
        self.http_client = httpx.AsyncClient(timeout=10.0)
    
    async def get_market_data(self, pair: str) -> Dict[str, Any]:
        """Get current market data for analysis."""
        try:
            response = await self.http_client.get(
                f"{self.base_url}:3001/snapshot",
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get market data: {e}")
            return {"error": str(e)}
    
    async def run_strategy(self, strategy_name: str, pair: str) -> Dict[str, Any]:
        """Run a strategy to get trading signal."""
        try:
            response = await self.http_client.post(
                f"{self.base_url}:3002/run",
                json={"strategy": strategy_name, "pair": pair},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to run strategy: {e}")
            return {"error": str(e)}
    
    async def check_risk(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """Check if decision passes risk constraints."""
        try:
            response = await self.http_client.post(
                f"{self.base_url}:3003/check",
                json=decision,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to check risk: {e}")
            return {"error": str(e)}
    
    async def get_strategy_performance(self) -> Dict[str, Any]:
        """Get recent performance of all strategies."""
        try:
            response = await self.http_client.get(
                f"{self.base_url}:3006/strategies/metrics",
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get strategy metrics: {e}")
            return {"error": str(e)}
    
    async def get_market_regime(self, pair: str) -> Dict[str, Any]:
        """Get current market regime classification."""
        try:
            response = await self.http_client.get(
                f"{self.base_url}:3006/regimes/{pair}?limit=1",
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            return data[0] if data else {"regime": "UNKNOWN"}
        except Exception as e:
            logger.error(f"Failed to get market regime: {e}")
            return {"error": str(e)}


class TradingLLMOrchestrator:
    """LLM-powered trading orchestrator using LangChain."""
    
    def __init__(self):
        if not LANGCHAIN_AVAILABLE:
            raise RuntimeError(
                "LangChain not installed. Install with: "
                "pip install langchain langchain-openai"
            )
        
        self.tools_manager = TradingTools()
        self.llm = ChatOpenAI(
            model_name=os.getenv("TRADING_MODEL", "gpt-4"),
            temperature=0.0,  # Deterministic for trading
            max_tokens=2048,
        )
        
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
        )
        
        self._setup_tools()
        self._create_agent()
    
    def _setup_tools(self) -> list:
        """Create tool functions for the agent."""
        
        @tool
        async def get_market_data(pair: str) -> str:
            """Get current market data for a trading pair."""
            data = await self.tools_manager.get_market_data(pair)
            return json.dumps(data)
        
        @tool
        async def run_strategy(strategy_name: str, pair: str) -> str:
            """Run a trading strategy for a pair."""
            result = await self.tools_manager.run_strategy(strategy_name, pair)
            return json.dumps(result)
        
        @tool
        async def check_risk(decision: str) -> str:
            """Check if a decision passes risk constraints."""
            decision_dict = json.loads(decision)
            result = await self.tools_manager.check_risk(decision_dict)
            return json.dumps(result)
        
        @tool
        async def get_strategy_performance() -> str:
            """Get recent performance metrics of all strategies."""
            metrics = await self.tools_manager.get_strategy_performance()
            return json.dumps(metrics)
        
        @tool
        async def get_market_regime(pair: str) -> str:
            """Get current market regime (TRENDING_UP, RANGE_BOUND, etc)."""
            regime = await self.tools_manager.get_market_regime(pair)
            return json.dumps(regime)
        
        self.tools = [
            get_market_data,
            run_strategy,
            check_risk,
            get_strategy_performance,
            get_market_regime,
        ]
    
    def _create_agent(self):
        """Create the LangChain agent."""
        
        system_prompt = """You are an expert trading orchestrator making critical trading decisions.

Your responsibilities:
1. Analyze market data and current regime
2. Select and run appropriate strategies
3. Evaluate strategy performance
4. Check risk constraints
5. Make final trade/skip decision with clear reasoning
6. Provide confidence score (0-1)

Decision Format:
- action: EXECUTE, SKIP, or WAIT
- confidence: 0-1 (0.8+ is high confidence)
- reasoning: Clear explanation of your decision
- risk_level: LOW, MEDIUM, or HIGH

Important:
- Always check market regime first
- Consider recent strategy performance
- Never execute if risk check fails
- Be conservative with confidence scores
- Explain trade-offs clearly"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        self.agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt,
        )
        
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            memory=self.memory,
            verbose=True,
            handle_parsing_errors=True,
        )
    
    async def make_trading_decision(
        self,
        pair: str,
        strategy_name: Optional[str] = None,
    ) -> TradingDecision:
        """Make an LLM-powered trading decision."""
        
        query = f"""
        Make a trading decision for pair: {pair}
        {f'Strategy: {strategy_name}' if strategy_name else ''}
        
        Steps:
        1. Get market data
        2. Check market regime
        3. Get strategy performance metrics
        4. Run appropriate strategy
        5. Check risk constraints
        6. Make final decision
        
        Return your decision with action, confidence, and reasoning.
        """
        
        try:
            result = await self.executor.ainvoke({"input": query})
            
            # Parse the LLM response into TradingDecision
            output = result.get("output", "")
            decision = self._parse_decision(output, pair)
            
            return decision
        except Exception as e:
            logger.error(f"Error making trading decision: {e}")
            # Return safe default
            return TradingDecision(
                action="SKIP",
                confidence=0.0,
                reasoning=f"Error in decision-making: {str(e)}",
                strategy="ERROR",
                pair=pair,
                side=None,
                quantity=None,
                risk_level="HIGH",
                alternative_strategies=[],
                market_condition="UNKNOWN",
            )
    
    def _parse_decision(self, response: str, pair: str) -> TradingDecision:
        """Parse LLM response into TradingDecision object."""
        
        # Simple parsing - in production, use JSON mode in LLM
        decision = TradingDecision(
            action="SKIP" if "skip" in response.lower() else "EXECUTE" if "execute" in response.lower() else "WAIT",
            confidence=0.7 if "high confidence" in response.lower() else 0.4,
            reasoning=response,
            strategy="multi_strategy",
            pair=pair,
            side="BUY" if "buy" in response.lower() else "SELL" if "sell" in response.lower() else None,
            quantity=None,
            risk_level="MEDIUM",
            alternative_strategies=[],
            market_condition="MIXED",
        )
        
        return decision


async def create_orchestrator() -> Optional[TradingLLMOrchestrator]:
    """Factory function to create orchestrator."""
    if not LANGCHAIN_AVAILABLE:
        logger.warning("LangChain not available - using fallback orchestrator")
        return None
    
    try:
        return TradingLLMOrchestrator()
    except Exception as e:
        logger.error(f"Failed to create LangChain orchestrator: {e}")
        return None


# Helper function for backward compatibility
async def make_langchain_decision(
    pair: str,
    strategy_name: Optional[str] = None,
) -> Optional[TradingDecision]:
    """Make a trading decision using LangChain (if available)."""
    
    orchestrator = await create_orchestrator()
    if not orchestrator:
        return None
    
    return await orchestrator.make_trading_decision(pair, strategy_name)
