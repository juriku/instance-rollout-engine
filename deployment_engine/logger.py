import logging

def setup_logging(level="INFO"):
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                       format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

def get_logger(name="deployment_engine"):
    return logging.getLogger(name)