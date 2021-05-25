from substrateinterface import SubstrateInterface
from cachetools import cachedmethod, TTLCache
from datetime import datetime

import pickle
import cachetools
import operator
import hashlib
import copy
import functools
import traceback


from .cache import TTLCacheStorage, hashkey


class SubstrateUtils(SubstrateInterface):

    def __init__(self, cache_ttl=0, cache_storage=None, cache_storage_sync_timer=0, **kwargs):
        self.cache = TTLCacheStorage(maxsize=1000, ttl=cache_ttl, storage=cache_storage, storage_sync_timer=cache_storage_sync_timer)
        super().__init__(**kwargs)


    @cachedmethod(operator.attrgetter('cache'), key=hashkey)
    def _query(self, module, storage_function, params=None, block_hash=None):
        print("[Request] _query >", module, storage_function, params)
        return self.query(module, storage_function, params, block_hash).value


    @cachedmethod(operator.attrgetter('cache'), key=hashkey)
    def _query_map(self, module, storage_function, params = None, block_hash = None, max_results = None, start_key = None, page_size = 100, ignore_decoding_errors = False):
        print("[Request] _query_map >", module, storage_function, params)
        data_map = self.query_map(module, storage_function, params, block_hash, max_results, start_key, page_size, ignore_decoding_errors)

        data = {}
        try:
            for k, v in data_map:
                if (k is not None and k.value not in data):
                    data[k.value] = v.value
                else:
                    None
        except:
            traceback.print_exc()

        return data


    def Query(self, module, storage_function, params=None, block_hash=None, debug=True):
        if debug:
            print('[Request] Query >', module, storage_function, params)
        data = self._query(module, storage_function, params, block_hash)
        return data


    def QueryMap(self, module, storage_function, params = None, block_hash = None, max_results = None, start_key = None, page_size = 100, ignore_decoding_errors = False, debug=True):
        if debug:
            print('[Request] QueryMap >', module, storage_function, params)
        data = self._query_map(module, storage_function, params, block_hash, max_results, start_key, page_size, ignore_decoding_errors)
        return data


    def SmartLedger(self, accountID):
        ledger = self.QueryMap('Staking', 'Ledger', page_size=1000, max_results=10000, ignore_decoding_errors=True, debug=False)

        if accountID in ledger.keys():
            data = copy.deepcopy(ledger[accountID])
            data['bonded'] = False
            return data

        bonded = self.QueryMap('Staking', 'Bonded', page_size=1000, max_results=10000, ignore_decoding_errors=True, debug=False)

        if (accountID in bonded.keys() and accountID is not bonded[accountID]):
            data = self.SmartLedger(bonded[accountID])
            data['bonded'] = True
            return data         

        if accountID not in ledger.keys():
            v = self.Query('Staking', 'Ledger', [accountID])
            if v is not None:
                ledger[accountID] = v
                data = copy.deepcopy(ledger[accountID])
                data['bonded'] = False
                return data

        if accountID not in bonded.keys():
            v = self.Query('Staking', 'Bonded', [accountID])
            if v is not None:
                bonded[accountID] = v  
                data = self.SmartLedger(bonded[accountID])
                data['bonded'] = True
                return data

        return None


    def EraInfo(self, era, filters={}):
        eraRewardsPoints = copy.deepcopy(self.QueryMap('Staking', 'ErasRewardPoints'))[era]
        if eraRewardsPoints is None:
            return None

        individual = {}
        for item in eraRewardsPoints['individual']:
            individual[item[0]] = item[1]
        eraRewardsPoints['individual'] = individual

        eraValidatotRewards = self.QueryMap('Staking', 'ErasValidatorReward')[era]
        if eraValidatotRewards is None:
            return None

        eraStakers = copy.deepcopy(self.QueryMap('Staking', 'ErasStakers', [era], page_size=1000, max_results=10000))

        stakeList = [eraStakers[k]['total'] for k in eraStakers]

        eraValidatorPrefs = self.QueryMap('Staking', 'ErasValidatorPrefs', [era], page_size=1000, max_results=10000)

        #dailyEras = 24 / (self.get_metadata_constant('Babe', 'EpochDuration').constant_value / 100)
        dailyEras = 4

        data = {
            'rewards': {
                'points': eraRewardsPoints['total'],
                'amount': eraValidatotRewards,
                'epr': eraValidatotRewards/sum(stakeList),
                'apr': eraValidatotRewards/sum(stakeList) * dailyEras * 365,
            },
            'stake': {
                'total': sum(stakeList),
                'min': min(stakeList),
                'max': max(stakeList)
            },
            'validators': {}
        } 

        for validatorID in eraStakers:
            amount_per_point = data['rewards']['amount'] / data['rewards']['points']

            if validatorID in eraRewardsPoints['individual'].keys():
                rewards_points = eraRewardsPoints['individual'][validatorID]
            else:
                rewards_points = 0

            rewards_amount = rewards_points * amount_per_point

            commission_percentage  = eraValidatorPrefs[validatorID]['commission']/(10**self.token_decimals)/100
            rewards_commission = rewards_amount * commission_percentage

            ledger = self.SmartLedger(validatorID)
            if (ledger is not None and era in ledger['claimedRewards']):
                rewards_claimed = True
            else:
                rewards_claimed = False

            data['validators'][validatorID] = {
                'rewards': {
                    'points': rewards_points,
                    'amount': rewards_amount,
                    'commission': rewards_commission,
                    'epr': rewards_amount/eraStakers[validatorID]['total'],
                    'apr': rewards_amount/eraStakers[validatorID]['total'] * dailyEras * 365,
                    'net_epr': (rewards_amount-rewards_commission)/eraStakers[validatorID]['total'],
                    'net_apr': (rewards_amount-rewards_commission)/eraStakers[validatorID]['total'] * dailyEras * 365,
                    'claimed': rewards_claimed,
                },
                'preferences': eraValidatorPrefs[validatorID],
                'stake': eraStakers[validatorID],
            }


            amount_per_stake = data['rewards']['amount'] / data['validators'][validatorID]['stake']['total']
            rewards_amount = data['validators'][validatorID]['stake']['own'] * amount_per_stake

            own = {
                'value': data['validators'][validatorID]['stake']['own'],
                'rewards': {
                    'amount': rewards_amount,
                    'commission': rewards_amount * commission_percentage,
                } 
            }

            data['validators'][validatorID]['stake']['nominators'] = {}
            for nominator in data['validators'][validatorID]['stake']['others']:
                rewards_amount = nominator['value'] * amount_per_stake

                nominator['rewards'] = {
                    'amount': rewards_amount,
                    'commission': rewards_amount * commission_percentage,
                }
                nominatorID = nominator['who']
                del nominator['who']
                data['validators'][validatorID]['stake']['nominators'][nominatorID] = nominator

            data['validators'][validatorID]['stake']['own'] = own
            del data['validators'][validatorID]['stake']['others']

        return data



    def ErasInfo(self, filters={}):
        data = {}

        if 'eras' in filters.keys():
            eras = sorted(set(filters['eras']))
        else:
            activeEra = self.Query('Staking', 'ActiveEra')['index']
            historyDepth = self.query('Staking', 'HistoryDepth').value
            eras = sorted(set(range(activeEra-historyDepth, activeEra)))

        for era in eras:
            eraInfo = self.EraInfo(era, filters)
            if eraInfo is not None:
                data[era] = eraInfo

        return data


    def ValidatorsInfo(self, filters={}, erasInfo=None):
        data = {}

        if erasInfo == None:
            erasInfo = self.ErasInfo(filters)

        erasInfo = copy.deepcopy(erasInfo)

        validators = self.QueryMap('Staking', 'Validators', page_size=1000, max_results=10000)
        nominators = self.QueryMap('Staking', 'Nominators', page_size=1000, max_results=10000)

        for validatorID in validators:
            ledger = self.SmartLedger(validatorID)
            if ledger is None:
                ledger = {
                    'total': 0,
                    'active': 0,
                }
            data[validatorID] = {
                'preferences': validators[validatorID],
                'stake': {
                    'active': ledger['active'],
                    'total': ledger['total'],
                    'own': ledger['total'],
                    'nominators': {},
                },
                'rewards': {},
                'eras': {},
            } 

            for era in erasInfo:
                if validatorID in erasInfo[era]['validators'].keys(): 
                    data[validatorID]['eras'][era] = erasInfo[era]['validators'][validatorID]

            for nominatorID in nominators:
                if validatorID in nominators[nominatorID]['targets']:
                    ledger = self.SmartLedger(nominatorID)
                    if ledger is None:
                        ledger = {
                            'total': 0,
                            'active': 0,
                        }
                    data[validatorID]['stake']['nominators'][nominatorID] = ledger['total']
                    data[validatorID]['stake']['total'] += ledger['total']


        return data

        for era in erasInfo:
            for validatorID in erasInfo[era]['validators']:
                if validatorID not in data:
                    data[validatorID] = {
                        'eras': {},
                        'nominators': {},
                        'preferences': validators[validatorID],
                    }
                data[validatorID]['eras'][era] = erasInfo[era]['validators'][validatorID]

        nominators = self.QueryMap('Staking', 'Nominators', page_size=1000, max_results=10000)

        for nominatorID in nominators:
            for validatorID in nominators[nominatorID]['targets']:
                if validatorID in data.keys():
                    ledger = self.SmartLedger(nominatorID)
                    if ledger is None:
                        ledger = {
                            'total': 0,
                            'active': 0,
                        }
                    data[validatorID]['nominators'][nominatorID] = ledger['total']

        for validatorID in data:
            data[validatorID]['rewards'] = {
                'points': functools.reduce(lambda a,b : a+data[validatorID]['eras'][b]['rewards']['points'] , data[validatorID]['eras'], 0),
                'amount': functools.reduce(lambda a,b : a+data[validatorID]['eras'][b]['rewards']['amount'] , data[validatorID]['eras'], 0),
                'unclaimed': functools.reduce(lambda a,b : a+[int(b)] if not data[validatorID]['eras'][b]['rewards']['claimed'] else a, data[validatorID]['eras'], []),
                'commission': functools.reduce(lambda a,b : a+data[validatorID]['eras'][b]['rewards']['commission'] , data[validatorID]['eras'], 0),
            }

        return data


    def NominatorsInfo(self, filters={}, erasInfo=None):
        data = {}

        if erasInfo == None:
            erasInfo = self.ErasInfo(filters)

        nominators = self.QueryMap('Staking', 'Nominators', page_size=1000, max_results=10000)

        for nominatorID in nominators:
            ledger = self.SmartLedger(nominatorID)
            if ledger is None:
                ledger = {
                    'total': 0,
                    'active': 0,
                }

            data[nominatorID] = {
                'eras': {},
                'stake': {
                    'total': ledger['total'],
                    'active:': ledger['active'],
                    'targets': nominators[nominatorID]['targets'],
                    #'submittedIn': nominators[nominatorID]['submittedIn'],
                }
            }

            for era in erasInfo:
                data[nominatorID]['eras'][era] = {
                    'validators': {},
                }

                for validatorID in erasInfo[era]['validators']:
                    if nominatorID in erasInfo[era]['validators'][validatorID]['stake']['nominators'].keys():
                       data[nominatorID]['eras'][era]['validators'][validatorID] = erasInfo[era]['validators'][validatorID]['stake']['nominators'][nominatorID]

        return data