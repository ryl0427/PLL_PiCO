import torch
from torch.utils.data import Dataset
import torchvision.transforms as transforms
import torchvision.datasets as dsets
from .randaugment import RandomAugment
# from .utils_algo import generate_uniform_cv_candidate_labels
import numpy as np
import random


def generate_uniform_cv_candidate_labels(train_labels, partial_rate=0.1, noisy_rate=0):
    '''
    if torch.min(train_labels) > 1:
        raise RuntimeError('testError')
    elif torch.min(train_labels) == 1:
        train_labels = train_labels - 1
    '''
    # K = int(torch.max(train_labels) - torch.min(train_labels) + 1)
    K = 8
    n = train_labels.shape[0]

    partialY = torch.zeros(n, K)
    # partialY[torch.arange(n), train_labels] = 1.0
    transition_matrix = np.eye(K) * (1 - noisy_rate)
    # inject label noise if noisy_rate > 0
    transition_matrix[np.where(~np.eye(transition_matrix.shape[0],dtype=bool))] = partial_rate
    print(transition_matrix)

    random_n = np.random.uniform(0, 1, size=(n, K))
    
    # To Do
    for j in range(n):  # for each instance
        random_n_j = random_n[j]
        while partialY[j].sum() == 0:
            if train_labels[j] < K:
                random_n_j = np.random.uniform(0, 1, size=(1, K))
                partialY[j] = torch.from_numpy((random_n_j <= transition_matrix[train_labels[j]]) * 1)
            else:
                label = random.randint(0, 7)
                random_n_j = np.random.uniform(0, 1, size=(1, K))
                partialY[j] = torch.from_numpy((random_n_j <= transition_matrix[label]) * 1)

    if noisy_rate == 0:
        partialY[torch.arange(n), train_labels] = 1.0
        # if supervised, reset the true label to be one.
        print('Reset true labels')

    print("Finish Generating Candidate Label Sets!\n")
    return partialY

def load_cifar10(partial_rate, batch_size, noisy_rate=0):
    test_transform = transforms.Compose(
            [transforms.ToTensor(),
            transforms.Normalize((0.4914, 0.4822, 0.4465), (0.247, 0.243, 0.261))])
    
    temp_train = dsets.CIFAR10(root='./data', train=True, download=True, transform=transforms.ToTensor())
    data, labels = temp_train.data, torch.Tensor(temp_train.targets).long()
    # get original data and labels

    test_dataset = dsets.CIFAR10(root='./data', train=False, transform=test_transform)
    test_loader = torch.utils.data.DataLoader(dataset=test_dataset, batch_size=batch_size*4, shuffle=False, num_workers=4,
        sampler=torch.utils.data.distributed.DistributedSampler(test_dataset, shuffle=False))
    # set test dataloader
    
    partialY = generate_uniform_cv_candidate_labels(labels, partial_rate, noisy_rate=noisy_rate)
    # generate partial labels
    
    '''
    temp = torch.zeros(partialY.shape)
    temp[torch.arange(partialY.shape[0]), labels] = 1
    if torch.sum(partialY * temp) == partialY.shape[0]:
        print('Running defualt PLL setting')
    else:
        print('Running noisy PLL setting')
    '''
    
    print('Average candidate num: ', partialY.sum(1).mean())
    partial_matrix_dataset = CIFAR10_Augmentention(data, partialY.float(), labels.float())
    # generate partial label dataset

    train_sampler = torch.utils.data.distributed.DistributedSampler(partial_matrix_dataset)
    partial_matrix_train_loader = torch.utils.data.DataLoader(dataset=partial_matrix_dataset, 
        batch_size=batch_size, 
        shuffle=(train_sampler is None), 
        num_workers=4,
        pin_memory=True,
        sampler=train_sampler,
        drop_last=True)
    return partial_matrix_train_loader, partialY, train_sampler, test_loader


class CIFAR10_Augmentention(Dataset):
    def __init__(self, images, given_label_matrix, true_labels):
        self.images = images
        self.given_label_matrix = given_label_matrix
        # user-defined label (partial labels)
        self.true_labels = true_labels
        self.weak_transform = transforms.Compose(
            [
            transforms.ToPILImage(),
            transforms.RandomResizedCrop(size=32, scale=(0.2, 1.)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomApply([
                transforms.ColorJitter(0.4, 0.4, 0.4, 0.1)
            ], p=0.8),
            transforms.RandomGrayscale(p=0.2),
            transforms.ToTensor(), 
            transforms.Normalize((0.4914, 0.4822, 0.4465), (0.247, 0.243, 0.261))])
        self.strong_transform = transforms.Compose(
            [
            transforms.ToPILImage(),
            transforms.RandomResizedCrop(size=32, scale=(0.2, 1.)),
            transforms.RandomHorizontalFlip(),
            RandomAugment(3, 5),
            transforms.ToTensor(), 
            transforms.Normalize((0.4914, 0.4822, 0.4465), (0.247, 0.243, 0.261))])

    def __len__(self):
        return len(self.true_labels)
        
    def __getitem__(self, index):
        each_image_w = self.weak_transform(self.images[index])
        each_image_s = self.strong_transform(self.images[index])
        each_label = self.given_label_matrix[index]
        each_true_label = self.true_labels[index]
        
        return each_image_w, each_image_s, each_label, each_true_label, index


