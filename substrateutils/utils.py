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



def hashkey(*args, **kwargs):
    new_args = []
    for i in range(0, len(args)):
       new_args.append(str(args[i]))
    args = tuple(new_args)

    for k in kwargs:
        kwargs[k] = str(kwargs[k])

    return(cachetools.keys.hashkey(*args, **kwargs))


class SubstrateUtils(SubstrateInterface):
    
    def __init__(self, cache_ttl=0, cache_storage=None, cache_storage_sync_timer=60, **kwargs):
        self.cache_ttl = cache_ttl
        self.cache_storage = cache_storage

        if self.cache_storage is None:
            self.cache = TTLCache(maxsize=None, ttl=cache_ttl)
        else:
            self.cache_storage_sync_timer = cache_storage_sync_timer
            self.cache_storage_next_time = datetime.timestamp(datetime.now()) + self.cache_storage_sync_timer
            try:
                with open(self.cache_storage, 'rb') as fh:
                    self.cache = pickle.load(fh)
            except:
                self.cache = TTLCache(maxsize=1000, ttl=cache_ttl) 

        self.ledger = None
        self.bonded = None 

        super().__init__(**kwargs)


    def _cache_storage_sync(self, force=False):
        now = datetime.timestamp(datetime.now())
        if self.cache_storage_next_time <= now or force:
            self.cache_storage_next_time = now + self.cache_storage_sync_timer
            with open(self.cache_storage, 'wb') as fh:
                pickle.dump(self.cache, fh)
            print("[Cache] Disk Sync")


    @cachedmethod(operator.attrgetter('cache'), key=hashkey)
    def _query(self, module, storage_function, params=None, block_hash=None):
        return self.query(module, storage_function, params, block_hash)


    @cachedmethod(operator.attrgetter('cache'), key=hashkey)
    def _query_map(self, module, storage_function, params = None, block_hash = None, max_results = None, start_key = None, page_size = 100, ignore_decoding_errors = False):
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


    def Query(self, module, storage_function, params=None, block_hash=None):
        print('[Request] Query >', module, storage_function, params)
        data = self.query(module, storage_function, params, block_hash)
        self._cache_storage_sync()
        return data


    def QueryMap(self, module, storage_function, params = None, block_hash = None, max_results = None, start_key = None, page_size = 100, ignore_decoding_errors = False):
        print('[Request] QueryMap >', module, storage_function, params)
        data = self._query_map(module, storage_function, params, block_hash, max_results, start_key, page_size, ignore_decoding_errors)
        self._cache_storage_sync()
        return data


    def EraInfo(self, era, filters={}):
        rewardsPoints = copy.deepcopy(self.QueryMap('Staking', 'ErasRewardPoints'))

        for e in rewardsPoints:
            individual = {}
            for item in rewardsPoints[e]['individual']:
                individual[item[0]]  = item[1]
                rewardsPoints[e]['individual'] = individual

        if era not in rewardsPoints.keys():
            return None

        validatotRewards = self.QueryMap('Staking', 'ErasValidatorReward')

        if era not in validatotRewards.keys():
            validatotRewards[era] = 0

        data = {
            'rewards': {
                'amount': validatotRewards[era],
                'points': rewardsPoints[era]['total'],
                'claimed': False,
            },
            'validators': {}
        }

        stakers = self.QueryMap('Staking', 'ErasStakers', [era], page_size=1000, max_results=10000)
        validatorPrefs = self.QueryMap('Staking', 'ErasValidatorPrefs', [era], page_size=1000, max_results=10000)

        for accountId in stakers:
            if ('accounts' in filters.keys() and accountId not in filters['accounts']):
                continue

            if accountId in rewardsPoints[era]['individual'].keys():
                rewards_points = rewardsPoints[era]['individual'][accountId]
            else:
                rewards_points = 0

            rewards_amount = (data['rewards']['amount']/data['rewards']['points']) * rewards_points

            commission_percentage  = (validatorPrefs[accountId]['commission']/1000000000)

            data['validators'][accountId] = {
                'rewards': {
                    'amount': rewards_amount,
                    'points': rewards_points,
                    'claimed': False,
                    'commission': rewards_amount * commission_percentage,
                },
                'stakers': stakers[accountId],
                'preferences': validatorPrefs[accountId]
            }

            for staker in data['validators'][accountId]['stakers']['others']:
                staker['reward'] = {
                    'amount': staker['value'] * (data['validators'][accountId]['rewards']['amount'] / data['validators'][accountId]['stakers']['total']),
                    'commission': staker['value'] * (data['validators'][accountId]['rewards']['amount'] / data['validators'][accountId]['stakers']['total']) * commission_percentage,
                }

        return data


    def ErasInfo(self, filters={}):
        data = {}

        if 'eras' in filters.keys():
            eras = sorted(set(filters['eras']))
        else:
            activeEra = self.Query('Staking', 'ActiveEra').value['index']
            #historyDepth = self.query('Staking', 'HistoryDepth').value
            historyDepth = 84
            eras = sorted(set(range(activeEra-historyDepth, activeEra)))

        for era in eras:
            eraInfo = self.EraInfo(era, filters)
            if eraInfo is not None:
                data[era] = eraInfo

        return data

    # TODO: check bonded field
    def SmartLedger(self, accountID):
        if self.ledger is None:
            self.ledger = self.QueryMap('Staking', 'Ledger', page_size=1000, max_results=10000, ignore_decoding_errors=True)
        if self.bonded is None:
            self.bonded = self.QueryMap('Staking', 'Bonded', page_size=1000, max_results=10000, ignore_decoding_errors=True)

        if accountID in self.ledger.keys():
            data = copy.deepcopy(self.ledger[accountID])
            data['bonded'] = False
            return data

        if (accountID in self.bonded.keys() and accountID is not self.bonded[accountID]):
            data = self.SmartLedger(self.bonded[accountID])
            data['bonded'] = True
            return data            

        if accountID not in self.ledger.keys():
            v = self.Query('Staking', 'Ledger', [accountID]).value
            if v is not None:
                self.ledger[accountID] = v
                data = copy.deepcopy(self.ledger[accountID])
                data['bonded'] = False
                return data

        if accountID not in self.bonded.keys():
            v = self.Query('Staking', 'Bonded', [accountID]).value
            if v is not None:
                self.bonded[accountID] = v  
                data = self.SmartLedger(self.bonded[accountID])
                data['bonded'] = True
                return data

        return None



    def ErasUpdateClaimed(self, data):
        skip = []

        for era in data:
            if data[era]['rewards']['claimed']:
                continue

            data[era]['rewards']['claimed'] = True

            for accountId in data[era]['validators']:

                if data[era]['validators'][accountId]['rewards']['claimed']:
                    continue

                if data[era]['validators'][accountId]['rewards']['points'] == 0:
                    data[era]['validators'][accountId]['rewards']['claimed'] = True
                    continue

                if accountId in skip:
                    continue

                ledger = self.SmartLedger(accountId)
                
                try: 
                    if era in ledger['claimedRewards']:
                        data[era]['validators'][accountId]['rewards']['claimed'] = True
                    else:
                        data[era]['validators'][accountId]['rewards']['claimed'] = False
                        data[era]['rewards']['claimed'] = False
                except:
                    data[era]['validators'][accountId]['rewards']['claimed'] = False
                    data[era]['rewards']['claimed'] = False
                    skip.append(accountId)

        return data



    def ValidatorsInfo(self, filters={}, erasInfo=None):
        data = {}

        if erasInfo == None:
            erasInfo = self.ErasInfo(filters)

        erasInfo = copy.deepcopy(erasInfo)

        for era in erasInfo:
            for accountID in erasInfo[era]['validators']:
                if accountID not in data:
                    data[accountID] = {
                        'eras': {},
                        'nominators': {},
                    }
                data[accountID]['eras'][era] = erasInfo[era]['validators'][accountID]

        nominators = self.QueryMap('Staking', 'Nominators', page_size=1000, max_results=10000)

        for nomAccountID in nominators:
            for accountID in nominators[nomAccountID]['targets']:
                if accountID in data.keys():
                    ledger = self.SmartLedger(nomAccountID)
                    if ledger is None:
                        ledger = {
                            'total': 0,
                            'active': 0,
                        }
                    data[accountID]['nominators'][nomAccountID] = ledger['total']

        return data


    def ValidatorsUpdateRewards(self, data):
        for validatorID in data:
            data[validatorID]['rewards'] = {
                'amount': functools.reduce(lambda a,b : a+data[validatorID]['eras'][b]['rewards']['amount'] , data[validatorID]['eras'], 0),
                'points': functools.reduce(lambda a,b : a+data[validatorID]['eras'][b]['rewards']['points'] , data[validatorID]['eras'], 0),
            }

        return data


    def NominatorsInfo(self, filters={}, validatorsInfo=None, erasInfo=None):


        data = self.QueryMap('Staking', 'Nominators', page_size=1000, max_results=10000)

        for nomAccountID in data:
            data[nomAccountID]['eras'] = {}

        if validatorsInfo == None:
            validatorsInfo = self.ValidatorsInfo(filters, erasInfo=erasInfo)

        validatorsInfo = copy.deepcopy(validatorsInfo)

        for accountID in validatorsInfo.keys():
            for era in validatorsInfo[accountID]['eras']:
                for staker in validatorsInfo[accountID]['eras'][era]['stakers']['others']:
                    nomAccountID = staker['who']
            
                    ledger = self.SmartLedger(nomAccountID)
                    if ledger is None:
                        ledger = {
                            'total': 0,
                            'active': 0,
                        }


                    if nomAccountID not in data:
                        data[nomAccountID] = {
                            'targets': [accountID],
                            'eras': {}
                        } 

                    data[nomAccountID]['stake'] = {
                        'total': ledger['total'],
                        'active': ledger['active'],
                    }

                    if era not in data[nomAccountID]['eras']:
                        data[nomAccountID]['eras'][era] = []
                    
                    del staker['who']
                    staker['validator'] = accountID
                    staker['reward'] = staker['value'] * (validatorsInfo[accountID]['eras'][era]['rewards']['amount'] / validatorsInfo[accountID]['eras'][era]['stakers']['total'])

                    data[nomAccountID]['eras'][era].append(staker)

        return data